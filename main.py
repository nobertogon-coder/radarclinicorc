import sqlite3
import re
import os
import unicodedata
from typing import List, Optional
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pypdf
import threading
import webbrowser
import uvicorn

app = FastAPI(title="Radar Clínico", description="Sistema de Apoio à Decisão Farmacêutica")

# ==============================================================================
# INICIALIZAÇÃO BLINDADA DA BASE DE DADOS
# ==============================================================================
def garantir_banco():
    precisa_recriar = False
    if not os.path.exists("radar_clinico.db"):
        precisa_recriar = True
    else:
        try:
            conn = sqlite3.connect("radar_clinico.db")
            cursor = conn.cursor()
            cursor.execute("SELECT diluente_padrao FROM antimicrobianos LIMIT 1")
            cursor.execute("SELECT 1 FROM antimicrobianos WHERE nome_generico = 'Cefazolina'")
            if not cursor.fetchone():
                precisa_recriar = True
            conn.close()
        except Exception:
            precisa_recriar = True

    if precisa_recriar:
        try:
            import setup_db
            setup_db.setup_database()
        except Exception as e:
            print("Aviso setup_db:", e)

    # Garante tabela de usuários e credenciais
    try:
        conn = sqlite3.connect("radar_clinico.db")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)
        cursor.execute("INSERT OR REPLACE INTO usuarios (username, password, role) VALUES ('Noberto', 'admin123', 'admin')")
        cursor.execute("INSERT OR REPLACE INTO usuarios (username, password, role) VALUES ('admin', 'admin123', 'admin')")
        conn.commit()
        conn.close()
    except Exception as e:
        print("Erro ao garantir tabela usuarios:", e)

garantir_banco()

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ==============================================================================
# FUNÇÕES UTILITÁRIAS E DE PROCESSAMENTO DE TEXTO (PLN)
# ==============================================================================
def sem_acentos(texto: str) -> str:
    if not texto:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")

def calcular_metricas(sexo: str, idade: int, peso_atual: float, altura_cm: float, creatinina: float):
    alt_m = altura_cm / 100.0
    imc = peso_atual / (alt_m ** 2) if alt_m > 0 else 0
    if sexo.lower() == "m":
        peso_ideal = 50.0 + 2.3 * ((altura_cm / 2.54) - 60)
    else:
        peso_ideal = 45.5 + 2.3 * ((altura_cm / 2.54) - 60)
        
    if peso_atual > (1.2 * peso_ideal):
        peso_adotado = peso_ideal + 0.4 * (peso_atual - peso_ideal)
    elif peso_atual < peso_ideal:
        peso_adotado = peso_atual
    else:
        peso_adotado = peso_ideal

    if creatinina > 0:
        clcr = ((140 - idade) * peso_adotado) / (72 * creatinina)
        if sexo.lower() == "f":
            clcr *= 0.85
    else:
        clcr = 0.0

    return {
        "imc": round(imc, 1),
        "peso_ideal": round(peso_ideal, 1),
        "peso_adotado": round(peso_adotado, 1),
        "clcr": round(clcr, 1)
    }

def limpar_texto_prescricao(texto: str) -> str:
    texto = re.sub(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', '[CPF OCULTO]', texto)
    texto = re.sub(r'(Prontuário|Prontuario|Registro|Atendimento|RG)[\s:]*([0-9A-Za-z\.\-]+)', r'\1: [RESTRITO]', texto, flags=re.IGNORECASE)
    texto = re.sub(r'(Paciente|Nome)[\s:]+([A-ZÀ-Úa-zà-ú\s]{4,40})', r'\1: [PACIENTE - LGPD]', texto, flags=re.IGNORECASE)
    return texto

def extrair_detalhes_linha(bloco_texto: str):
    bloco_limpo = " ".join(bloco_texto.split())
    dia = ""
    m_dia = re.search(r'\b[dD]\s*[-:]?\s*(\d{1,2})(?:/\d{1,2})?\b', bloco_limpo)
    if m_dia:
        dia = f"D{m_dia.group(1)}"
    else:
        m_dia2 = re.search(r'(\d{1,2})\s*[ºo°]?\s*dia\b', bloco_limpo, re.IGNORECASE)
        if m_dia2:
            dia = f"D{m_dia2.group(1)}"

    dose_str = ""
    m_dose = re.search(r'(\d+(?:[\.,]\d+)?\s*(?:mg|g|ui|mcg))', bloco_limpo, re.IGNORECASE)
    if m_dose:
        dose_str = m_dose.group(1).replace(" ", "")

    freq_str = ""
    m_freq = re.search(r'(\b(?:6/6h?|8/8h?|12/12h?|24/24h?|48/48h?|1x\s*ao\s*dia|2x\s*ao\s*dia|3x\s*ao\s*dia|4x\s*ao\s*dia|a\s*cada\s*\d+\s*h(?:oras)?|de\s*\d+/\d+\s*h?|\b\d{1,2}h\b))', bloco_limpo, re.IGNORECASE)
    if m_freq:
        freq_str = m_freq.group(1)

    posologia = f"{dose_str} {freq_str}".strip()

    diluentes_achados = []
    padroes_diluente = [
        (r'\b(?:sf|soro\s*fisiologico)\s*(?:0[,\.]9\s*%?)?\s*(?:\d+\s*ml)?', 'SF 0,9%'),
        (r'\b(?:sg|soro\s*glicosado|glicose)\s*(?:5\s*%?)?\s*(?:\d+\s*ml)?', 'SG 5%'),
        (r'\b(?:ad|abd|agua\s*destilada|agua\s*p/?\s*inj(?:ecao|etaveis)?)\s*(?:\d+\s*ml)?', 'Água Destilada (AD)'),
        (r'\b(?:rl|ringer\s*(?:lactato)?)\s*(?:\d+\s*ml)?', 'Ringer Lactato')
    ]
    bloco_sem_acento = sem_acentos(bloco_limpo.lower())
    for regex_padrao, nome_padrao in padroes_diluente:
        m_dil = re.search(regex_padrao, bloco_sem_acento, re.IGNORECASE)
        if m_dil:
            m_vol = re.search(r'(\d{2,3}\s*ml)', m_dil.group(0), re.IGNORECASE)
            if not m_vol:
                m_vol = re.search(r'(\d{2,3}\s*ml)', bloco_sem_acento, re.IGNORECASE)
            vol_txt = f" {m_vol.group(1).upper()}" if m_vol else ""
            diluentes_achados.append(f"{nome_padrao}{vol_txt}")

    m_via = re.search(r'\b(EV|IV|IM|VO|SNE|SNG|SC|endovenoso|intravenoso)\b', bloco_limpo, re.IGNORECASE)
    via_str = m_via.group(1).upper() if m_via else ""

    diluente_final = " + ".join(dict.fromkeys(diluentes_achados))
    if via_str and via_str not in diluente_final:
        diluente_final = f"{via_str} | {diluente_final}" if diluente_final else via_str

    return {"dia": dia, "poso": posologia, "diluente": diluente_final}

# ==============================================================================
# INTERFACE HTML
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Radar Clínico - Triagem Farmacêutica</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
    <style>
        :root {
            --brand-primary: #0056b3; 
            --brand-light: #e0f2fe;
            --brand-dark: #003d82;
            --brand-nova-triagem: #0dcaf0;
            --bg-login: #3b4252;
            --bg-dashboard: #f3f4f6;
        }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: var(--bg-dashboard); color: #374151; }
        
        #login-view { background-color: var(--bg-login); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-card { background: #fff; width: 100%; max-width: 400px; border-radius: 12px; padding: 2.5rem; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }
        .login-logo-box { background: #f8fafc; border-radius: 12px; padding: 15px; display: inline-block; margin-bottom: 15px; }
        .login-logo { height: 80px; object-fit: contain; }
        .badge-acesso { background-color: var(--brand-light); color: var(--brand-primary); font-weight: 700; letter-spacing: 0.5px; font-size: 0.75rem; padding: 6px 12px; border-radius: 20px; }
        
        .navbar-radar { background-color: var(--brand-primary); padding: 8px 24px; min-height: 64px; }
        .nav-logo-box { background: white; border-radius: 8px; width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; padding: 4px; flex-shrink: 0; }
        .nav-logo { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; }
        .btn-nova-triagem { background-color: var(--brand-nova-triagem); color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 0.85rem; letter-spacing: 0.5px; text-transform: uppercase; font-weight: 700; }
        .btn-nova-triagem:hover { background-color: #0bacce; color: white; }
        
        .nav-metric-box { text-align: right; line-height: 1.2; }
        .nav-metric-label { font-size: 0.65rem; font-weight: 800; color: rgba(255,255,255,0.85); text-transform: uppercase; letter-spacing: 0.5px; }
        .nav-metric-value { font-size: 1.05rem; font-weight: 800; color: white; }
        .nav-alert-value { font-size: 1.05rem; font-weight: 800; color: #ffc107; }
        
        .btn-admin-nav { background-color: rgba(0,0,0,0.25); color: white; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 8px 16px; font-size: 0.85rem; font-weight: 700; }
        .btn-admin-nav:hover { background-color: rgba(0,0,0,0.4); color: white; }
        .btn-sair { background-color: #dc3545; color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 0.85rem; font-weight: 700; }
        .btn-sair:hover { background-color: #bb2d3b; color: white; }

        .form-label-custom { font-size: 0.72rem; font-weight: 700; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.2rem; display: block; }
        .form-control-custom { border-radius: 8px; border: 1px solid #d1d5db; padding: 8px 12px; font-size: 0.88rem; }
        .btn-brand { background-color: var(--brand-primary); color: white; border: none; border-radius: 8px; font-weight: 600; padding: 10px 15px; }
        .btn-brand:hover { background-color: var(--brand-dark); color: white; }
        .card-dash { border: none; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 20px; background: white; border-top: 4px solid var(--brand-primary); }
        .card-title-dash { font-size: 0.9rem; font-weight: 700; color: var(--brand-primary); text-transform: uppercase; margin-bottom: 1rem; display: flex; align-items: center; }
        .step-number { background: var(--brand-light); color: var(--brand-primary); width: 24px; height: 24px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; margin-right: 10px; flex-shrink: 0; font-weight: 800; }
        .metric-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center; }
        .metric-value { font-size: 1.8rem; font-weight: 800; color: var(--brand-primary); margin: 5px 0; }
        .soap-output { font-family: 'Consolas', monospace; font-size: 0.88rem; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; padding: 15px; width: 100%; min-height: 480px; resize: vertical; }
        .d-none { display: none !important; }
        
        .slot-container { background: white; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; margin-bottom: 10px; border-left: 4px solid var(--brand-primary); }
        .slot-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
        .slot-row > select { flex: 3; }
        .slot-row > input.dia-input { flex: 1; max-width: 90px; }

        .select2-container--default .select2-selection--multiple {
            border: 1px solid #d1d5db;
            border-radius: 8px;
            min-height: 40px;
            padding: 2px 6px;
        }
        .select2-container--default .select2-selection--multiple .select2-selection__choice {
            background-color: var(--brand-light);
            border: 1px solid #bae6fd;
            color: var(--brand-dark);
            border-radius: 6px;
            padding: 2px 8px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .tag-btn {
            display: inline-block;
            padding: 4px 10px;
            margin: 2px;
            font-size: 0.78rem;
            font-weight: 600;
            color: #4b5563;
            background-color: #f3f4f6;
            border: 1px solid #e5e7eb;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .tag-btn:hover { background-color: #e5e7eb; }
        
        .btn-extrair {
            background-color: #1e293b;
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 700;
            padding: 11px;
            width: 100%;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-size: 0.85rem;
        }
        .btn-extrair:hover { background-color: #0f172a; color: white; }

        .custom-file-upload {
            border: 1px solid #86efac;
            background-color: #dcfce7;
            color: #166534;
            display: inline-block;
            padding: 7px 14px;
            cursor: pointer;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.82rem;
            white-space: nowrap;
        }
        .custom-file-upload:hover { background-color: #bbf7d0; }
        input[type="file"] { display: none; }
        .file-name-display { font-size: 0.82rem; color: #6b7280; margin-left: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    </style>
</head>
<body>

<!-- LOGIN -->
<div id="login-view">
    <div class="login-card text-center">
        <div class="login-logo-box"><img src="/static/logo.jpg" alt="Logo" class="login-logo" onerror="this.src='https://via.placeholder.com/80?text=LOGO'"></div>
        <div class="mb-4"><span class="badge-acesso">ACESSO FARMACÊUTICO</span></div>
        <form id="loginForm" onsubmit="event.preventDefault(); fazerLogin();" class="text-start">
            <div class="mb-3"><label class="form-label-custom">Usuário</label><input type="text" class="form-control form-control-custom" id="user" required></div>
            <div class="mb-3"><label class="form-label-custom">Senha</label><input type="password" class="form-control form-control-custom" id="pass" required></div>
            <div id="loginError" class="text-danger small mb-3 fw-bold d-none">Usuário ou senha inválidos.</div>
            <button type="submit" class="btn-brand w-100 py-3">Entrar no Sistema</button>
        </form>
    </div>
</div>

<!-- DASHBOARD -->
<div id="app-view" class="d-none">
    <nav class="navbar navbar-radar d-flex justify-content-between align-items-center">
        <div class="d-flex align-items-center gap-3">
            <div class="nav-logo-box"><img src="/static/logo.jpg" class="nav-logo" alt="Logo" onerror="this.style.display='none'"></div>
            <button class="btn-nova-triagem" onclick="novaTriagem()"><i class="bi bi-arrow-clockwise me-1"></i> Nova Triagem</button>
        </div>
        <div class="d-flex align-items-center gap-4">
            <div class="d-flex align-items-center gap-4 me-2">
                <div class="nav-metric-box">
                    <div class="nav-metric-label">CLCR Calculado</div>
                    <div class="nav-metric-value" id="navClcr">-- mL/min</div>
                </div>
                <div class="nav-metric-box">
                    <div class="nav-metric-label">Alertas Gerais</div>
                    <div class="nav-alert-value" id="navAlertas">0</div>
                </div>
            </div>
            <div class="d-flex align-items-center gap-2">
                <button id="btnAdmin" class="btn-admin-nav d-none" data-bs-toggle="modal" data-bs-target="#adminModal"><i class="bi bi-person me-1"></i> ADMIN (ADMIN)</button>
                <button class="btn-sair" onclick="fazerLogout()"><i class="bi bi-box-arrow-right me-1"></i> Sair</button>
            </div>
        </div>
    </nav>

    <div class="container-fluid p-4" style="max-width: 1400px;">
        <div class="row g-4">
            <!-- Bloco 1: Perfil & Risco -->
            <div class="col-lg-4">
                <div class="card card-dash p-3 h-100">
                    <div class="card-title-dash"><span class="step-number">1</span> Perfil & Risco</div>
                    <div class="row g-2">
                        <div class="col-6"><label class="form-label-custom">Idade (Anos)</label><input type="number" id="idade" class="form-control form-control-custom" value="65"></div>
                        <div class="col-6"><label class="form-label-custom">Sexo Biológico</label><select id="sexo" class="form-select form-control-custom"><option value="m">Masculino</option><option value="f">Feminino</option></select></div>
                    </div>
                    
                    <label class="form-label-custom mt-3">Comorbidades Clássicas</label>
                    <select class="form-select" id="comorbidadesSelect" multiple="multiple">
                        <option value="Acamado">Acamado</option>
                        <option value="HAS">HAS</option>
                        <option value="DM">DM</option>
                        <option value="DRC">DRC</option>
                        <option value="IC">IC</option>
                        <option value="Demência">Demência</option>
                        <option value="Parkinson">Parkinson</option>
                        <option value="DPOC">DPOC</option>
                        <option value="Hepatopatia">Hepatopatia Grave</option>
                    </select>
                    <div class="mt-2">
                        <span class="tag-btn" onclick="addComorbidade('HAS')">+ HAS</span>
                        <span class="tag-btn" onclick="addComorbidade('DM')">+ DM</span>
                        <span class="tag-btn" onclick="addComorbidade('DRC')">+ DRC</span>
                        <span class="tag-btn" onclick="addComorbidade('IC')">+ IC</span>
                        <span class="tag-btn" onclick="addComorbidade('Demência')">+ Demência</span>
                        <span class="tag-btn" onclick="addComorbidade('Parkinson')">+ Parkinson</span>
                        <span class="tag-btn" onclick="addComorbidade('DPOC')">+ DPOC</span>
                        <span class="tag-btn" onclick="addComorbidade('Hepatopatia')">+ Hepatopatia</span>
                        <span class="tag-btn" onclick="addComorbidade('Acamado')">+ Acamado</span>
                    </div>
                </div>
            </div>

            <!-- Bloco 2: Função Renal & Antropometria -->
            <div class="col-lg-4">
                <div class="card card-dash p-3 h-100">
                    <div class="card-title-dash"><span class="step-number">2</span> Função Renal & Antropometria</div>
                    <div class="row g-2 mb-3">
                        <div class="col-4"><label class="form-label-custom">Creat. (mg/dL)</label><input type="number" step="0.1" id="creatinina" class="form-control form-control-custom" value="1.2"></div>
                        <div class="col-4"><label class="form-label-custom">Peso (kg)</label><input type="number" id="peso" class="form-control form-control-custom" value="70"></div>
                        <div class="col-4"><label class="form-label-custom">Altura (cm)</label><input type="number" id="altura" class="form-control form-control-custom" value="170"></div>
                    </div>
                    <div class="metric-box">
                        <div class="form-label-custom text-muted" style="font-size: 0.65rem;">DEPURAÇÃO ESTIMADA (COCKCROFT-GAULT)</div>
                        <div class="metric-value" id="valClcr">-- <span style="font-size:1rem;">mL/min</span></div>
                        <div class="small fw-bold text-secondary mt-1">Peso Adotado: <span id="valPesoAdotado">--</span> kg</div>
                    </div>
                </div>
            </div>

            <!-- Bloco 3: Entrada da Prescrição -->
            <div class="col-lg-4">
                <div class="card card-dash p-3 h-100">
                    <div class="card-title-dash"><span class="step-number">3</span> Entrada da Prescrição</div>
                    
                    <label class="form-label-custom text-muted">Prescrição em PDF</label>
                    <div class="mb-2 d-flex align-items-center">
                        <label class="custom-file-upload">
                            <input type="file" id="pdfFile" accept=".pdf" onchange="updateFileName(this)">
                            Escolher arquivo
                        </label>
                        <span id="fileNameDisplay" class="file-name-display">Nenhum arquivo escolhido</span>
                    </div>

                    <label class="form-label-custom text-muted mt-1">Ou cole a prescrição (Opcional)</label>
                    <textarea id="textoManual" class="form-control form-control-custom mb-2" rows="3" placeholder="Cole o texto da prescrição aqui se necessário..."></textarea>
                    <input type="hidden" id="textoBrutoOculto">
                    
                    <button class="btn-extrair mt-auto" type="button" onclick="extrairPdf()"><i class="bi bi-magic me-2"></i> Extrair Prescrição</button>
                    <div id="statusExtracao" class="small fw-bold text-success mt-1 d-none"></div>
                </div>
            </div>
            
            <!-- Bloco 4: Terapêutica Antimicrobiana & Avaliação Clínica SOAP -->
            <div class="col-12">
                <div class="card card-dash p-3">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <div class="card-title-dash mb-0"><span class="step-number">4</span> Terapêutica Antimicrobiana & Avaliação Clínica SOAP</div>
                        <button class="btn btn-brand px-4 py-2 fs-6" onclick="gerarAnalise()"><i class="bi bi-play-fill me-1"></i> AVALIAR PRESCRIÇÃO</button>
                    </div>
                    <div class="row g-4">
                        <div class="col-lg-5">
                            <div class="bg-light p-3 rounded border">
                                <label class="form-label-custom mb-2 text-primary">Antimicrobianos (Fármaco, Dia, Posologia e Diluente)</label>
                                
                                <!-- SLOT 1 -->
                                <div class="slot-container">
                                    <div class="slot-row">
                                        <select id="slot1" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 1 --</option></select>
                                        <input type="text" id="slot1_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)">
                                    </div>
                                    <div class="row g-1">
                                        <div class="col-6">
                                            <input type="text" id="slot1_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia (Ex: 1g 8/8h)">
                                        </div>
                                        <div class="col-6">
                                            <input type="text" id="slot1_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente (Ex: SF 0,9% 100mL)">
                                        </div>
                                    </div>
                                </div>

                                <!-- SLOT 2 -->
                                <div class="slot-container">
                                    <div class="slot-row">
                                        <select id="slot2" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 2 --</option></select>
                                        <input type="text" id="slot2_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)">
                                    </div>
                                    <div class="row g-1">
                                        <div class="col-6">
                                            <input type="text" id="slot2_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia (Ex: 1g 12/12h)">
                                        </div>
                                        <div class="col-6">
                                            <input type="text" id="slot2_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente (Ex: SF 0,9% 250mL)">
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- SLOT 3 -->
                                <div class="slot-container">
                                    <div class="slot-row">
                                        <select id="slot3" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 3 --</option></select>
                                        <input type="text" id="slot3_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)">
                                    </div>
                                    <div class="row g-1">
                                        <div class="col-6">
                                            <input type="text" id="slot3_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia (Ex: 2g 8/8h)">
                                        </div>
                                        <div class="col-6">
                                            <input type="text" id="slot3_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente (Ex: SG 5% 100mL)">
                                        </div>
                                    </div>
                                </div>

                                <!-- SLOT 4 -->
                                <div class="slot-container">
                                    <div class="slot-row">
                                        <select id="slot4" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 4 --</option></select>
                                        <input type="text" id="slot4_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)">
                                    </div>
                                    <div class="row g-1">
                                        <div class="col-6">
                                            <input type="text" id="slot4_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia (Ex: 500mg 8/8h)">
                                        </div>
                                        <div class="col-6">
                                            <input type="text" id="slot4_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente (Ex: Bolsa Pronta)">
                                        </div>
                                    </div>
                                </div>

                                <!-- Demais Medicamentos Extraídos -->
                                <div class="mt-3 pt-2 border-top">
                                    <label class="form-label-custom text-secondary"><i class="bi bi-capsule me-1"></i> Demais Medicamentos da Prescrição (Auto-Extraídos)</label>
                                    <textarea id="outrosMedicamentos" class="form-control form-control-custom" rows="2" placeholder="Dipirona, Enoxaparina, Omeprazol, etc. aparecerão aqui automaticamente ao extrair o PDF..."></textarea>
                                </div>
                            </div>
                        </div>
                        
                        <div class="col-lg-7 position-relative">
                            <button class="btn btn-sm btn-outline-secondary position-absolute top-0 end-0 m-2 fw-bold" style="z-index: 10;" onclick="copiarSoap()"><i class="bi bi-copy"></i> Copiar SOAP</button>
                            <textarea id="parecerSoap" class="soap-output pt-5" readonly placeholder="Aguardando dados clínicos para gerar o parecer estruturado, julgamento posológico e checagem de diluentes..."></textarea>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- MODAL ADMIN -->
<div class="modal fade" id="adminModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header bg-light">
        <h5 class="modal-title fw-bold" style="color: var(--brand-primary);"><i class="bi bi-person-plus-fill"></i> Gerenciar Usuários</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
      </div>
      <div class="modal-body">
        <div class="mb-3"><label class="form-label-custom">Novo Usuário</label><input type="text" id="novoUser" class="form-control form-control-custom"></div>
        <div class="mb-3"><label class="form-label-custom">Nova Senha</label><input type="password" id="novoPass" class="form-control form-control-custom"></div>
        <div id="adminMsg" class="small fw-bold mb-2"></div>
        <button class="btn btn-brand w-100" onclick="criarUsuario()">Cadastrar</button>
      </div>
    </div>
  </div>
</div>

<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
<script>
$(document).ready(function() {
    $('#comorbidadesSelect').select2({ placeholder: "Selecione ou digite...", allowClear: true, width: '100%' });
});

function addComorbidade(tag) {
    let select = $('#comorbidadesSelect');
    let vals = select.val() || [];
    if (!vals.includes(tag)) {
        vals.push(tag);
        select.val(vals).trigger('change');
    }
}

function updateFileName(input) {
    const display = document.getElementById('fileNameDisplay');
    if (input.files && input.files.length > 0) {
        let name = input.files[0].name;
        display.innerText = name.length > 25 ? name.substring(0, 12) + '...' + name.substring(name.length - 8) : name;
    } else {
        display.innerText = "Nenhum arquivo escolhido";
    }
}

async function fazerLogin() {
    const user = document.getElementById('user').value.trim().toLowerCase();
    const pass = document.getElementById('pass').value.trim();
    
    // BYPASS SEGURO PARA ENTRAR DIRETO
    if ((user === 'noberto' || user === 'admin') && (pass === 'admin123' || pass === 'admin')) {
        document.getElementById('login-view').classList.add('d-none');
        document.getElementById('app-view').classList.remove('d-none');
        document.getElementById('btnAdmin').classList.remove('d-none');
        carregarCatalogo();
        return;
    }

    try {
        const res = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: user, password: pass }) });
        const data = await res.json();
        if (data.success) {
            document.getElementById('login-view').classList.add('d-none'); document.getElementById('app-view').classList.remove('d-none');
            if (data.role === 'admin') document.getElementById('btnAdmin').classList.remove('d-none');
            carregarCatalogo();
        } else { document.getElementById('loginError').classList.remove('d-none'); }
    } catch (e) {
        document.getElementById('loginError').innerText = "Erro de comunicação com o servidor.";
        document.getElementById('loginError').classList.remove('d-none');
    }
}

function fazerLogout() {
    document.getElementById('app-view').classList.add('d-none'); document.getElementById('login-view').classList.remove('d-none');
    document.getElementById('user').value = ''; document.getElementById('pass').value = '';
    document.getElementById('loginError').classList.add('d-none'); document.getElementById('btnAdmin').classList.add('d-none');
    novaTriagem();
}

function novaTriagem() {
    document.getElementById('idade').value = '65'; document.getElementById('peso').value = '70';
    document.getElementById('altura').value = '170'; document.getElementById('creatinina').value = '1.2';
    $('#comorbidadesSelect').val(null).trigger('change');
    
    document.getElementById('pdfFile').value = ''; 
    document.getElementById('fileNameDisplay').innerText = "Nenhum arquivo escolhido";
    document.getElementById('textoManual').value = '';
    document.getElementById('textoBrutoOculto').value = '';
    document.getElementById('outrosMedicamentos').value = ''; 
    document.getElementById('parecerSoap').value = '';
    document.getElementById('statusExtracao').classList.add('d-none');
    
    document.getElementById('valClcr').innerHTML = '-- <span style="font-size:1rem;">mL/min</span>';
    document.getElementById('navClcr').innerText = '-- mL/min';
    document.getElementById('navAlertas').innerText = '0';
    document.getElementById('valPesoAdotado').innerText = '--';
    
    ['slot1', 'slot2', 'slot3', 'slot4'].forEach(id => {
        document.getElementById(id).value = '';
        document.getElementById(id+'_d').value = '';
        document.getElementById(id+'_poso').value = '';
        document.getElementById(id+'_dil').value = '';
    });
}

async function criarUsuario() {
    const user = document.getElementById('novoUser').value; const pass = document.getElementById('novoPass').value;
    if (!user || !pass) return alert("Preencha ambos os campos.");
    const res = await fetch("/api/usuarios", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: user, password: pass }) });
    const data = await res.json();
    const msg = document.getElementById('adminMsg');
    if (data.success) {
        msg.className = "small fw-bold mb-2 text-success"; msg.innerText = "Usuário cadastrado com sucesso!";
        document.getElementById('novoUser').value = ''; document.getElementById('novoPass').value = '';
    } else { msg.className = "small fw-bold mb-2 text-danger"; msg.innerText = data.msg; }
}

async function carregarCatalogo() {
    try {
        const res = await fetch("/api/antimicrobianos");
        const catalogo = await res.json();
        const selects = [document.getElementById("slot1"), document.getElementById("slot2"), document.getElementById("slot3"), document.getElementById("slot4")];
        selects.forEach(select => {
            select.innerHTML = `<option value="">-- Antimicrobiano --</option>`;
            catalogo.forEach(item => {
                const opt = document.createElement("option");
                opt.value = item.nome;
                opt.innerText = item.nome;
                select.appendChild(opt);
            });
        });
    } catch(e) {
        console.error("Erro ao carregar catálogo", e);
    }
}

async function extrairPdf() {
    const fileInput = document.getElementById("pdfFile");
    const textoManualInput = document.getElementById("textoManual").value;
    
    let formData = new FormData();
    if (fileInput.files[0]) {
        formData.append("file", fileInput.files[0]);
    } else if (textoManualInput.trim() !== "") {
        formData.append("texto", textoManualInput);
    } else {
        return alert("Selecione um arquivo PDF ou cole o texto da prescrição.");
    }
    
    const res = await fetch("/api/extrair-pdf", { method: "POST", body: formData });
    if (!res.ok) {
        alert("Erro no servidor. Verifique o console ou os logs da Render.");
        return;
    }
    const data = await res.json();
    
    document.getElementById("textoBrutoOculto").value = data.texto_anonimizado;
    document.getElementById("outrosMedicamentos").value = data.outros_meds.join(", ");
    
    const slots = ["slot1", "slot2", "slot3", "slot4"];
    slots.forEach(id => {
        document.getElementById(id).value = "";
        document.getElementById(id+"_d").value = "";
        document.getElementById(id+"_poso").value = "";
        document.getElementById(id+"_dil").value = "";
    });
    
    for (let i = 0; i < data.atbs.length && i < 4; i++) {
        document.getElementById(slots[i]).value = data.atbs[i].nome;
        document.getElementById(slots[i]+"_d").value = data.atbs[i].dia || "";
        document.getElementById(slots[i]+"_poso").value = data.atbs[i].poso || "";
        document.getElementById(slots[i]+"_dil").value = data.atbs[i].diluente || "";
    }

    const st = document.getElementById("statusExtracao");
    st.innerText = `Extraído: ${data.atbs.length} antimicrobiano(s) e ${data.outros_meds.length} outro(s) medicamento(s).`;
    st.classList.remove("d-none");
}

async function gerarAnalise() {
    const comorbs = $('#comorbidadesSelect').val() || [];
    
    const atbs = [];
    ['slot1', 'slot2', 'slot3', 'slot4'].forEach(id => {
        const nome = document.getElementById(id).value;
        if(nome) {
            atbs.push({
                nome: nome,
                dia: document.getElementById(id+'_d').value,
                poso: document.getElementById(id+'_poso').value,
                diluente: document.getElementById(id+'_dil').value
            });
        }
    });
    
    const textoBrutoTotal = document.getElementById("textoBrutoOculto").value + "\n" + document.getElementById("textoManual").value;

    const payload = {
        sexo: document.getElementById("sexo").value,
        idade: parseInt(document.getElementById("idade").value) || 0,
        peso: parseFloat(document.getElementById("peso").value) || 0,
        altura: parseFloat(document.getElementById("altura").value) || 0,
        creatinina: parseFloat(document.getElementById("creatinina").value) || 0,
        comorbidades: comorbs,
        antimicrobianos: atbs,
        outros_medicamentos_texto: document.getElementById("outrosMedicamentos").value,
        texto_prescricao_bruto: textoBrutoTotal
    };

    const res = await fetch("/api/avaliar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await res.json();

    document.getElementById("valClcr").innerHTML = data.metricas.clcr + ' <span style="font-size:1rem;">mL/min</span>';
    document.getElementById("navClcr").innerText = data.metricas.clcr + " mL/min";
    document.getElementById("navAlertas").innerText = data.alertas_count;
    document.getElementById("valPesoAdotado").innerText = data.metricas.peso_adotado;
    document.getElementById("parecerSoap").value = data.soap;
}

function copiarSoap() {
    const txt = document.getElementById("parecerSoap"); txt.select(); navigator.clipboard.writeText(txt.value);
}
</script>
</body>
</html>
"""

# ==============================================================================
# ROTAS DA API
# ==============================================================================
class ATBSlot(BaseModel):
    nome: str
    dia: str
    poso: str
    diluente: Optional[str] = ""

class AvaliacaoPayload(BaseModel):
    sexo: str
    idade: int
    peso: float
    altura: float
    creatinina: float
    comorbidades: List[str]
    antimicrobianos: List[ATBSlot]
    outros_medicamentos_texto: str
    texto_prescricao_bruto: str

class LoginData(BaseModel):
    username: str
    password: str

class NovoUsuario(BaseModel):
    username: str
    password: str
    role: str = "user"

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_TEMPLATE

@app.get("/teste-login")
def teste_login():
    return {"status": "Login direto ativo para Noberto / admin123"}

@app.post("/api/login")
def login(data: LoginData):
    u = data.username.strip().lower()
    p = data.password.strip()
    
    if (u == "noberto" and p in ["admin123", "admin"]) or (u == "admin" and p in ["admin123", "admin"]):
        return {"success": True, "role": "admin"}

    try:
        garantir_banco()
        conn = sqlite3.connect("radar_clinico.db")
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM usuarios WHERE LOWER(username) = ? AND password = ?", (u, p))
        user = cursor.fetchone()
        conn.close()
        if user:
            return {"success": True, "role": user[0]}
        return {"success": False}
    except Exception:
        return {"success": False}

@app.post("/api/usuarios")
def criar_usuario(data: NovoUsuario):
    try:
        garantir_banco()
        conn = sqlite3.connect("radar_clinico.db")
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO usuarios (username, password, role) VALUES (?, ?, ?)", (data.username.strip(), data.password.strip(), data.role))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception:
        return {"success": False, "msg": "Erro ao salvar usuário."}

@app.get("/api/antimicrobianos")
def get_antimicrobianos():
    garantir_banco()
    conn = sqlite3.connect("radar_clinico.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome_generico, nomes_comerciais FROM antimicrobianos ORDER BY nome_generico ASC")
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    for r in rows:
        nome_exibicao = f"{r[1]} ({r[2]})" if r[2] else r[1]
        items.append({"id": r[0], "nome": nome_exibicao, "nome_generico": r[1]})
    return items

@app.post("/api/extrair-pdf")
async def processar_pdf(file: Optional[UploadFile] = File(None), texto: Optional[str] = Form(None)):
    garantir_banco()
    texto_bruto = ""
    if file:
        reader = pypdf.PdfReader(file.file)
        paginas = []
        for p in reader.pages:
            try:
                paginas.append(p.extract_text(extraction_mode="layout") or p.extract_text() or "")
            except Exception:
                paginas.append(p.extract_text() or "")
        texto_bruto = "\n".join(paginas)
    elif texto:
        texto_bruto = texto
        
    texto_anon = limpar_texto_prescricao(texto_bruto)
    
    # ERRO CORRIGIDO AQUI: l.strip() em vez de l.string
    linhas_originais = [l.strip() for l in texto_anon.splitlines() if l.strip()]
    palavras_negacao = ["suspender", "suspenso", "suspensa", "alergia", "alergico", "nao administrar"]
    linhas_validas = []
    for linha in linhas_originais:
        linha_norm = sem_acentos(linha.lower())
        if not any(neg in linha_norm for neg in palavras_negacao):
            linhas_validas.append(linha)

    texto_limpo_norm = sem_acentos(" ".join(linhas_validas).lower())
    
    conn = sqlite3.connect("radar_clinico.db")
    cursor = conn.cursor()
    cursor.execute("SELECT nome_generico, nomes_comerciais, diluente_padrao FROM antimicrobianos")
    atbs_db = cursor.fetchall()
    conn.close()
    
    atbs_encontrados = []
    genes_ja_incluidos = set()

    sinonimos_extras = {
        "Cefazolina": ["cefazolina", "kefazol", "cezolin"],
        "Piperacilina + Tazobactam": ["piperacilina", "tazobactam", "tazocin"],
        "Ampicilina + Sulbactam": ["sulbactam", "unasyn"],
        "Amoxicilina + Clavulanato": ["clavulanato", "clavulin"],
        "Imipenem + Cilastatina": ["imipenem", "tienam"],
        "Sulfametoxazol + Trimetoprima": ["sulfametoxazol", "trimetoprima", "bactrim"],
        "Ceftazidima + Avibactam": ["avibactam", "zavicefta"],
        "Polimixina B": ["polimixina b", "polimixina", "bedfordpoly"],
        "Anfotericina B Lipossomal": ["ambisome", "lipossomal"],
        "Anfotericina B Desoxicolato": ["fungizon", "desoxicolato"]
    }

    for idx, linha in enumerate(linhas_validas):
        linha_norm = sem_acentos(linha.lower())
        bloco_contexto = linha
        if idx + 1 < len(linhas_validas):
            bloco_contexto += " " + linhas_validas[idx + 1]
        if idx + 2 < len(linhas_validas):
            bloco_contexto += " " + linhas_validas[idx + 2]

        for gen, com, dil_padrao in atbs_db:
            if gen in genes_ja_incluidos:
                continue
            termos_busca = [sem_acentos(gen.lower())]
            if com:
                termos_busca.extend([sem_acentos(c.strip().lower()) for c in com.split(",")])
            if gen in sinonimos_extras:
                termos_busca.extend(sinonimos_extras[gen])

            achou = False
            for termo in termos_busca:
                if termo and re.search(r'\b' + re.escape(termo) + r'\b', linha_norm):
                    achou = True
                    break
            if achou:
                genes_ja_incluidos.add(gen)
                detalhes = extrair_detalhes_linha(bloco_contexto)
                nome_formatado = f"{gen} ({com})" if com else gen
                atbs_encontrados.append({
                    "nome": nome_formatado,
                    "dia": detalhes["dia"],
                    "poso": detalhes["poso"],
                    "diluente": detalhes["diluente"] if detalhes["diluente"] else dil_padrao
                })

    dicionario_comuns = [
        "dipirona", "paracetamol", "tramadol", "morfina", "fentanil", "metadona", "codeina",
        "cetoprofeno", "tenoxicam", "dexketoprofeno",
        "omeprazol", "pantoprazol", "esomeprazol", "ranitidina", "famotidina",
        "ondansetrona", "bromoprida", "metoclopramida", "dimenidrinato",
        "enoxaparina", "heparina", "rivaroxabana", "apixabana", "varfarina", "clopidogrel", "aas", "acido acetilsalicilico",
        "furosemida", "espironolactona", "hidroclorotiazida",
        "losartana", "enalapril", "captopril", "anlodipino", "nifedipino", "hidralazina", "clonidina",
        "metoprolol", "carvedilol", "atenolol", "propranolol", "amiodarona", "digoxina",
        "sinvastatina", "atorvastatina", "rosuvastatina",
        "insulina", "metformina", "gliclazida", "sitagliptina", "dapagliflozina", "empagliflozina",
        "hidrocortisona", "dexametasona", "metilprednisolona", "prednisona", "prednisolona",
        "fenitoina", "acido valproico", "valproato", "levetiracetam", "carbamazepina", "fenobarbital",
        "haloperidol", "quetiapina", "risperidona", "olanzapina", "clorpromazina",
        "diazepam", "midazolam", "clonazepam", "lorazepam", "dexmedetomidina",
        "escitalopram", "sertralina", "fluoxetina", "venlafaxina", "trazodona", "amitriptilina",
        "pregabalina", "gabapentina", "levodopa", "biperideno",
        "salbutamol", "ipratropio", "fenoterol", "budesonida", "acetilcisteina",
        "lactulose", "bisacodil", "simeticona", "loperamida",
        "noradrenalina", "norepinefrina", "dobutamina", "dopamina", "vasopressina", "nitroprussiato", "nitroglicerina",
        "cloreto de potassio", "gluconato de calcio", "sulfato de magnesio", "bicarbonato de sodio", "levotiroxina"
    ]
    
    comuns_encontrados = []
    for med in dicionario_comuns:
        if re.search(r'\b' + re.escape(med) + r'\b', texto_limpo_norm):
            nome_cap = med.title()
            if nome_cap not in comuns_encontrados:
                comuns_encontrados.append(nome_cap)

    return {
        "texto_anonimizado": texto_anon,
        "atbs": atbs_encontrados,
        "outros_meds": comuns_encontrados
    }

def extrair_mg_da_posologia(posologia: str) -> float:
    if not posologia:
        return 0.0
    poso_norm = posologia.lower().replace(".", "").replace(",", ".")
    match_dose = re.search(r'(\d+(?:\.\d+)?)\s*(mg|g|ui)', poso_norm)
    if not match_dose:
        return 0.0
    
    dose = float(match_dose.group(1))
    unidade = match_dose.group(2)
    if unidade == 'g':
        dose *= 1000.0
        
    freq_multiplicador = 1.0
    if re.search(r'(6/6|6h|4x)', poso_norm):
        freq_multiplicador = 4.0
    elif re.search(r'(8/8|8h|3x)', poso_norm):
        freq_multiplicador = 3.0
    elif re.search(r'(12/12|12h|2x)', poso_norm):
        freq_multiplicador = 2.0
    elif re.search(r'(48/48|48h)', poso_norm):
        freq_multiplicador = 0.5
        
    return dose * freq_multiplicador

@app.post("/api/avaliar")
def avaliar_paciente(payload: AvaliacaoPayload):
    garantir_banco()
    metricas = calcular_metricas(payload.sexo, payload.idade, payload.peso, payload.altura, payload.creatinina)
    clcr = metricas["clcr"]
    texto_bruto_norm = sem_acentos(payload.texto_prescricao_bruto.lower())
    alertas_count = 0
    
    conn = sqlite3.connect("radar_clinico.db")
    cursor = conn.cursor()
    
    avaliacoes = []
    farmacotecnias = []
    incompatibilidades_encontradas = set()
    
    for atb in payload.antimicrobianos:
        nome_generico = atb.nome.split(" (")[0]
        cursor.execute("SELECT * FROM antimicrobianos WHERE nome_generico = ?", (nome_generico,))
        row = cursor.fetchone()
        if row:
            max_padrao, max_30_50, max_10_30, max_10 = row[4], row[5], row[6], row[7]
            dil_recomendado, monit, farm_info = row[8], row[9], row[10]
            
            if clcr >= 50:
                limite_diario_permitido = max_padrao
            elif 30 <= clcr < 50:
                limite_diario_permitido = max_30_50
            elif 10 <= clcr < 30:
                limite_diario_permitido = max_10_30
            else:
                limite_diario_permitido = max_10
                
            dose_diaria_digitada = extrair_mg_da_posologia(atb.poso)
            
            if dose_diaria_digitada == 0:
                status_julgamento = f"Pendente de posologia (Teto p/ ClCr {clcr} mL/min: {limite_diario_permitido}mg/dia)"
            elif dose_diaria_digitada > limite_diario_permitido:
                status_julgamento = f"ALERTA [!]: SOBREDOSE RENAL ({int(dose_diaria_digitada)}mg/dia excede o limite de {limite_diario_permitido}mg/dia p/ ClCr {clcr} mL/min)."
                alertas_count += 1
            else:
                status_julgamento = f"Posologia ADEQUADA para função renal ({int(dose_diaria_digitada)}mg/dia <= Teto {limite_diario_permitido}mg/dia)."

            alerta_tempo = ""
            m_d = re.search(r'(\d+)', atb.dia or "")
            if m_d and int(m_d.group(1)) >= 8:
                alerta_tempo = f" | [ALERTA TEMPO D{m_d.group(1)}: Avaliar descalonamento ou término]"
                alertas_count += 1

            dil_usuario = (atb.diluente or "").strip()
            alerta_dil_slot = ""
            dil_norm = sem_acentos(dil_usuario.lower())
            if dil_norm:
                cursor.execute("SELECT condicao, alerta FROM regras_farmacotecnicas WHERE LOWER(farmaco) = LOWER(?)", (sem_acentos(nome_generico.lower()),))
                for cond_regra, msg_alerta in cursor.fetchall():
                    if cond_regra.lower() in dil_norm:
                        alerta_dil_slot = f" | [INCOMPATIBILIDADE DILUENTE: {msg_alerta}]"
                        incompatibilidades_encontradas.add(f"[ALERTA FARMACOTÉCNICO] {nome_generico.upper()} em {dil_usuario.upper()}: {msg_alerta}")

            str_dia = f" ({atb.dia})" if atb.dia else ""
            str_dil = f" | Diluente/Via: {dil_usuario}" if dil_usuario else f" | Diluente sugerido: {dil_recomendado}"
            avaliacoes.append(f"       * {nome_generico}{str_dia} [{atb.poso if atb.poso else 'Posologia não informada'}]{str_dil} -> {status_julgamento}{alerta_tempo}{alerta_dil_slot}")
            farmacotecnias.append(f"• {nome_generico} (Monitorar: {monit}): {farm_info}")

    riscos_comorbidade = set()
    if payload.comorbidades:
        cursor.execute("SELECT comorbidade, farmaco_contraindicado, alerta FROM comorbidades_risco")
        todas_regras_risco = cursor.fetchall()
        
        nomes_atbs_usados = [sem_acentos(a.nome.lower()) for a in payload.antimicrobianos]
        outros_meds_usados = sem_acentos(payload.outros_medicamentos_texto.lower()) + " " + texto_bruto_norm
        
        for doenca_paciente in payload.comorbidades:
            for comorb_regra, farmaco_regra, alerta_regra in todas_regras_risco:
                if sem_acentos(comorb_regra.lower()) == sem_acentos(doenca_paciente.lower()):
                    farm_norm = sem_acentos(farmaco_regra.lower())
                    if any(farm_norm in atb for atb in nomes_atbs_usados) or farm_norm in outros_meds_usados:
                        riscos_comorbidade.add(f"[RISCO POR COMORBIDADE - {doenca_paciente.upper()}] {farmaco_regra}: {alerta_regra}")
                        alertas_count += 1

    interacoes_detectadas = set()
    cursor.execute("SELECT droga_a, droga_b, gravidade, mecanismo, conduta FROM interacoes")
    todas_interacoes = cursor.fetchall()
    contexto_farmacos = " ".join([sem_acentos(a.nome.lower()) + " " + sem_acentos((a.diluente or "").lower()) for a in payload.antimicrobianos]) + " " + sem_acentos(payload.outros_medicamentos_texto.lower()) + " " + texto_bruto_norm
    for d_a, d_b, grav, mec, cond in todas_interacoes:
        if sem_acentos(d_a.lower()) in contexto_farmacos and sem_acentos(d_b.lower()) in contexto_farmacos:
            interacoes_detectadas.add(f"[INTERAÇÃO {grav.upper()}] {d_a} + {d_b}: {mec}. Conduta: {cond}")
            alertas_count += 1

    cursor.execute("SELECT farmaco, condicao, alerta FROM regras_farmacotecnicas")
    regras = cursor.fetchall()
    linhas_prescricao = texto_bruto_norm.splitlines()
    for farmaco, condicao, alerta in regras:
        for linha in linhas_prescricao:
            if re.search(r'\b' + re.escape(farmaco.lower()) + r'\b', linha) and re.search(r'\b' + re.escape(condicao.lower()) + r'\b', linha):
                incompatibilidades_encontradas.add(f"[ALERTA FARMACOTÉCNICO] {farmaco.upper()} + {condicao.upper()}: {alerta}")
                
    alertas_count += len(incompatibilidades_encontradas)
    conn.close()

    is_acamado = "Acamado" in payload.comorbidades
    meds_gerais = sem_acentos(payload.outros_medicamentos_texto.lower()) + " " + texto_bruto_norm
    
    tem_heparina = any(h in meds_gerais for h in ["heparina", "enoxaparina", "versan", "clexane", "rivaroxabana", "apixabana", "varfarina"])
    tem_ibp = any(i in meds_gerais for i in ["omeprazol", "pantoprazol", "esomeprazol"])
    
    if not tem_heparina and (payload.idade >= 60 or is_acamado):
        alerta_tev = "ALERTA [!]: Paciente de risco (Idoso/Acamado) SEM profilaxia anticoagulante prescrita. Avaliar omissão ou contraindicação."
        alertas_count += 1
    else:
        alerta_tev = "Conforme (Baixo risco ou profilaxia anticoagulante ativa)."
        
    if tem_ibp:
        alerta_lamg = "ALERTA [!]: Protetor gástrico (IBP) ativo na enfermaria. Reavaliar indicação formal para eventual desprescrição segura."
        alertas_count += 1
    else:
        alerta_lamg = "Conforme (Sem uso desnecessário de IBP)."

    soap = [
        "=== EVOLUÇÃO FARMACÊUTICA // RADAR CLÍNICO ===",
        "[S] SUBJETIVO: Acompanhamento farmacoterapêutico de enfermaria. Triagem clínica da prescrição médica.",
        "[O] OBJETIVO:",
        f"    - Idade: {payload.idade} anos | Sexo: {payload.sexo.upper()} | Peso Real: {payload.peso} kg | Altura: {payload.altura} cm | IMC: {metricas['imc']} kg/m²",
        f"    - Função Renal (Cockcroft-Gault): {metricas['clcr']} mL/min (Peso Adotado: {metricas['peso_adotado']} kg)",
        f"    - Comorbidades / Fatores: {', '.join(payload.comorbidades) if payload.comorbidades else 'Nenhum assinalado'}",
        f"    - Outros Medicamentos em Uso: {payload.outros_medicamentos_texto if payload.outros_medicamentos_texto else 'Nenhum listado'}",
        "[A] AVALIAÇÃO FARMACÊUTICA:"
    ]
    
    soap.append("    1. Terapêutica Antimicrobiana (Julgamento Posológico Renal e Diluição):")
    if avaliacoes:
        for a in avaliacoes:
            soap.append(a)
    else: 
        soap.append("       * Nenhum antimicrobiano submetido à avaliação.")
    
    soap.append("    2. Profilaxias Institucionais (Triagem por Exceção):")
    soap.append(f"       * TEV: {alerta_tev}")
    soap.append(f"       * LAMG: {alerta_lamg}")

    if interacoes_detectadas:
        soap.append("    3. Interações Medicamentosas Relevantes:")
        for inter in interacoes_detectadas:
            soap.append(f"       * {inter}")

    if riscos_comorbidade:
        soap.append("    4. Alertas de Segurança por Comorbidades:")
        for risco in riscos_comorbidade:
            soap.append(f"       * {risco}")

    if incompatibilidades_encontradas:
        soap.append("    5. Incompatibilidades Farmacotécnicas e Vias:")
        for inc in incompatibilidades_encontradas:
            soap.append(f"       * {inc}")

    soap.append("[P] PLANO DE CUIDADO FARMACÊUTICO:")
    soap.append("    1. Discutir intervenções e ajustes posológicos com a equipe médica/enfermagem conforme alertas acima.")
    if farmacotecnias:
        soap.append("    2. Recomendações Técnicas de Reconstituição, Diluição e Tempo de Infusão:")
        for f in farmacotecnias:
            soap.append(f"       {f}")

    return {"metricas": metricas, "soap": "\n".join(soap), "alertas_count": alertas_count}

@app.get("/setup-manual")
def setup_manual():
    try:
        import setup_db
        setup_db.setup_database()
        return {"mensagem": "Base de dados recriada com sucesso com 35 antimicrobianos e credenciais Noberto / admin123!"}
    except Exception as e:
        return {"erro": str(e)}

if __name__ == "__main__":
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="warning")
