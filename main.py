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
import uvicorn
import setup_db

app = FastAPI(title="Radar Clínico")

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

setup_db.setup_database()

def sem_acentos(texto: str) -> str:
    if not texto: return ""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")

def calcular_metricas(sexo: str, idade: int, peso_atual: float, altura_cm: float, creatinina: float):
    alt_m = altura_cm / 100.0
    imc = peso_atual / (alt_m ** 2) if alt_m > 0 else 0
    peso_ideal = (50.0 if sexo.lower() == "m" else 45.5) + 2.3 * ((altura_cm / 2.54) - 60)
    peso_adotado = (peso_ideal + 0.4 * (peso_atual - peso_ideal)) if peso_atual > (1.2 * peso_ideal) else (peso_atual if peso_atual < peso_ideal else peso_ideal)
    clcr = (((140 - idade) * peso_adotado) / (72 * creatinina)) * (0.85 if sexo.lower() == "f" else 1.0) if creatinina > 0 else 0.0
    return {"imc": round(imc, 1), "peso_ideal": round(peso_ideal, 1), "peso_adotado": round(peso_adotado, 1), "clcr": round(clcr, 1)}

def limpar_texto_prescricao(texto: str) -> str:
    texto = re.sub(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', '[CPF OCULTO]', texto)
    texto = re.sub(r'(Prontuário|Prontuario|Registro|Atendimento|RG)[\s:]*([0-9A-Za-z\.\-]+)', r'\1: [RESTRITO]', texto, flags=re.IGNORECASE)
    return re.sub(r'(Paciente|Nome)[\s:]+([A-ZÀ-Úa-zà-ú\s]{4,40})', r'\1: [PACIENTE - LGPD]', texto, flags=re.IGNORECASE)

def extrair_detalhes_linha(bloco_texto: str):
    bloco_limpo = " ".join(bloco_texto.split())
    dia = ""
    m_dia = re.search(r'\b[dD]\s*[-:]?\s*(\d{1,2})(?:/\d{1,2})?\b', bloco_limpo) or re.search(r'(\d{1,2})\s*[ºo°]?\s*dia\b', bloco_limpo, re.IGNORECASE)
    if m_dia: dia = f"D{m_dia.group(1)}"

    m_dose = re.search(r'(\d+(?:[\.,]\d+)?\s*(?:mg|g|ui|mcg))', bloco_limpo, re.IGNORECASE)
    dose_str = m_dose.group(1).replace(" ", "") if m_dose else ""
    m_freq = re.search(r'(\b(?:6/6h?|8/8h?|12/12h?|24/24h?|48/48h?|1x\s*ao\s*dia|2x\s*ao\s*dia|3x\s*ao\s*dia|4x\s*ao\s*dia|a\s*cada\s*\d+\s*h(?:oras)?|\b\d{1,2}h\b))', bloco_limpo, re.IGNORECASE)
    posologia = f"{dose_str} {m_freq.group(1) if m_freq else ''}".strip()

    diluentes_achados = []
    padroes = [(r'\b(?:sf|soro\s*fisiologico)\s*(?:0[,\.]9\s*%?)?\s*(?:\d+\s*ml)?', 'SF 0,9%'), (r'\b(?:sg|soro\s*glicosado|glicose)\s*(?:5\s*%?)?\s*(?:\d+\s*ml)?', 'SG 5%'), (r'\b(?:ad|abd|agua\s*destilada)\s*(?:\d+\s*ml)?', 'Água Destilada (AD)'), (r'\b(?:rl|ringer\s*lactato)\s*(?:\d+\s*ml)?', 'Ringer Lactato')]
    bloco_sa = sem_acentos(bloco_limpo.lower())
    for reg, nom in padroes:
        if re.search(reg, bloco_sa, re.IGNORECASE):
            m_vol = re.search(r'(\d{2,3}\s*ml)', bloco_sa, re.IGNORECASE)
            diluentes_achados.append(f"{nom}{' ' + m_vol.group(1).upper() if m_vol else ''}")

    m_via = re.search(r'\b(EV|IV|IM|VO|SNE|SNG|SC)\b', bloco_limpo, re.IGNORECASE)
    via_str = m_via.group(1).upper() if m_via else ""
    dil_final = " + ".join(dict.fromkeys(diluentes_achados))
    if via_str and via_str not in dil_final: dil_final = f"{via_str} | {dil_final}" if dil_final else via_str
    return {"dia": dia, "poso": posologia, "diluente": dil_final}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Radar Clínico - Triagem Farmacêutica</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
    <style>
        :root { --brand-primary: #0056b3; --brand-light: #e0f2fe; --brand-dark: #003d82; --brand-nova-triagem: #0dcaf0; --bg-login: #3b4252; --bg-dashboard: #f3f4f6; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: var(--bg-dashboard); color: #374151; }
        #login-view { background-color: var(--bg-login); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-card { background: #fff; width: 100%; max-width: 400px; border-radius: 12px; padding: 2.5rem; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }
        .login-logo-box { background: #f8fafc; border-radius: 12px; padding: 15px; display: inline-block; margin-bottom: 15px; }
        .login-logo { height: 80px; object-fit: contain; }
        .badge-acesso { background-color: var(--brand-light); color: var(--brand-primary); font-weight: 700; font-size: 0.75rem; padding: 6px 12px; border-radius: 20px; }
        .navbar-radar { background-color: var(--brand-primary); padding: 8px 24px; min-height: 64px; }
        .nav-logo-box { background: white; border-radius: 8px; width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; padding: 4px; }
        .nav-logo { max-width: 100%; max-height: 100%; object-fit: contain; border-radius: 6px; }
        .btn-nova-triagem { background-color: var(--brand-nova-triagem); color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 0.85rem; text-transform: uppercase; font-weight: 700; }
        .nav-metric-box { text-align: right; line-height: 1.2; }
        .nav-metric-label { font-size: 0.65rem; font-weight: 800; color: rgba(255,255,255,0.85); text-transform: uppercase; }
        .nav-metric-value { font-size: 1.05rem; font-weight: 800; color: white; }
        .nav-alert-value { font-size: 1.05rem; font-weight: 800; color: #ffc107; }
        .btn-admin-nav { background-color: rgba(0,0,0,0.25); color: white; border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 8px 16px; font-size: 0.85rem; font-weight: 700; }
        .btn-sair { background-color: #dc3545; color: white; border: none; border-radius: 6px; padding: 8px 16px; font-size: 0.85rem; font-weight: 700; }
        .form-label-custom { font-size: 0.72rem; font-weight: 700; color: #6b7280; text-transform: uppercase; margin-bottom: 0.2rem; display: block; }
        .form-control-custom { border-radius: 8px; border: 1px solid #d1d5db; padding: 8px 12px; font-size: 0.88rem; }
        .btn-brand { background-color: var(--brand-primary); color: white; border: none; border-radius: 8px; font-weight: 600; padding: 10px 15px; }
        .card-dash { border: none; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 20px; background: white; border-top: 4px solid var(--brand-primary); }
        .card-title-dash { font-size: 0.9rem; font-weight: 700; color: var(--brand-primary); text-transform: uppercase; margin-bottom: 1rem; display: flex; align-items: center; }
        .step-number { background: var(--brand-light); color: var(--brand-primary); width: 24px; height: 24px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; margin-right: 10px; font-weight: 800; }
        .metric-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 15px; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center; }
        .metric-value { font-size: 1.8rem; font-weight: 800; color: var(--brand-primary); margin: 5px 0; }
        .soap-output { font-family: 'Consolas', monospace; font-size: 0.88rem; border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; padding: 15px; width: 100%; min-height: 480px; resize: vertical; }
        .d-none { display: none !important; }
        .slot-container { background: white; border: 1px solid #cbd5e1; border-radius: 8px; padding: 10px; margin-bottom: 10px; border-left: 4px solid var(--brand-primary); }
        .slot-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
        .slot-row > select { flex: 3; }
        .slot-row > input.dia-input { flex: 1; max-width: 90px; }
        .tag-btn { display: inline-block; padding: 4px 10px; margin: 2px; font-size: 0.78rem; font-weight: 600; color: #4b5563; background-color: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 20px; cursor: pointer; }
        .btn-extrair { background-color: #1e293b; color: white; border: none; border-radius: 8px; font-weight: 700; padding: 11px; width: 100%; text-transform: uppercase; font-size: 0.85rem; }
        .custom-file-upload { border: 1px solid #86efac; background-color: #dcfce7; color: #166534; display: inline-block; padding: 7px 14px; cursor: pointer; border-radius: 20px; font-weight: 700; font-size: 0.82rem; }
        input[type="file"] { display: none; }
        .file-name-display { font-size: 0.82rem; color: #6b7280; margin-left: 10px; }
    </style>
</head>
<body>
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
<div id="app-view" class="d-none">
    <nav class="navbar navbar-radar d-flex justify-content-between align-items-center">
        <div class="d-flex align-items-center gap-3">
            <div class="nav-logo-box"><img src="/static/logo.jpg" class="nav-logo" alt="Logo" onerror="this.style.display='none'"></div>
            <button class="btn-nova-triagem" onclick="novaTriagem()"><i class="bi bi-arrow-clockwise me-1"></i> Nova Triagem</button>
        </div>
        <div class="d-flex align-items-center gap-4">
            <div class="d-flex align-items-center gap-4 me-2">
                <div class="nav-metric-box"><div class="nav-metric-label">CLCR Calculado</div><div class="nav-metric-value" id="navClcr">-- mL/min</div></div>
                <div class="nav-metric-box"><div class="nav-metric-label">Alertas Gerais</div><div class="nav-alert-value" id="navAlertas">0</div></div>
            </div>
            <div class="d-flex align-items-center gap-2">
                <button id="btnAdmin" class="btn-admin-nav d-none" data-bs-toggle="modal" data-bs-target="#adminModal"><i class="bi bi-person me-1"></i> ADMIN (ADMIN)</button>
                <button class="btn-sair" onclick="fazerLogout()"><i class="bi bi-box-arrow-right me-1"></i> Sair</button>
            </div>
        </div>
    </nav>
    <div class="container-fluid p-4" style="max-width: 1400px;">
        <div class="row g-4">
            <div class="col-lg-4">
                <div class="card card-dash p-3 h-100">
                    <div class="card-title-dash"><span class="step-number">1</span> Perfil & Risco</div>
                    <div class="row g-2">
                        <div class="col-6"><label class="form-label-custom">Idade (Anos)</label><input type="number" id="idade" class="form-control form-control-custom" value="65"></div>
                        <div class="col-6"><label class="form-label-custom">Sexo Biológico</label><select id="sexo" class="form-select form-control-custom"><option value="m">Masculino</option><option value="f">Feminino</option></select></div>
                    </div>
                    <label class="form-label-custom mt-3">Comorbidades Clássicas</label>
                    <select class="form-select" id="comorbidadesSelect" multiple="multiple">
                        <option value="Acamado">Acamado</option><option value="HAS">HAS</option><option value="DM">DM</option>
                        <option value="DRC">DRC</option><option value="IC">IC</option><option value="Demência">Demência</option>
                        <option value="Parkinson">Parkinson</option><option value="DPOC">DPOC</option><option value="Hepatopatia">Hepatopatia Grave</option>
                    </select>
                    <div class="mt-2">
                        <span class="tag-btn" onclick="addComorbidade('HAS')">+ HAS</span><span class="tag-btn" onclick="addComorbidade('DM')">+ DM</span>
                        <span class="tag-btn" onclick="addComorbidade('DRC')">+ DRC</span><span class="tag-btn" onclick="addComorbidade('IC')">+ IC</span>
                        <span class="tag-btn" onclick="addComorbidade('Demência')">+ Demência</span><span class="tag-btn" onclick="addComorbidade('Parkinson')">+ Parkinson</span>
                        <span class="tag-btn" onclick="addComorbidade('DPOC')">+ DPOC</span><span class="tag-btn" onclick="addComorbidade('Hepatopatia')">+ Hepatopatia</span>
                        <span class="tag-btn" onclick="addComorbidade('Acamado')">+ Acamado</span>
                    </div>
                </div>
            </div>
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
            <div class="col-lg-4">
                <div class="card card-dash p-3 h-100">
                    <div class="card-title-dash"><span class="step-number">3</span> Entrada da Prescrição</div>
                    <label class="form-label-custom text-muted">Prescrição em PDF</label>
                    <div class="mb-2 d-flex align-items-center">
                        <label class="custom-file-upload"><input type="file" id="pdfFile" accept=".pdf" onchange="updateFileName(this)">Escolher arquivo</label>
                        <span id="fileNameDisplay" class="file-name-display">Nenhum arquivo escolhido</span>
                    </div>
                    <label class="form-label-custom text-muted mt-1">Ou cole a prescrição (Opcional)</label>
                    <textarea id="textoManual" class="form-control form-control-custom mb-2" rows="3" placeholder="Cole o texto da prescrição aqui se necessário..."></textarea>
                    <input type="hidden" id="textoBrutoOculto">
                    <button class="btn-extrair mt-auto" type="button" onclick="extrairPdf()"><i class="bi bi-magic me-2"></i> Extrair Prescrição</button>
                    <div id="statusExtracao" class="small fw-bold text-success mt-1 d-none"></div>
                </div>
            </div>
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
                                <div class="slot-container"><div class="slot-row"><select id="slot1" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 1 --</option></select><input type="text" id="slot1_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)"></div><div class="row g-1"><div class="col-6"><input type="text" id="slot1_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia"></div><div class="col-6"><input type="text" id="slot1_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente"></div></div></div>
                                <div class="slot-container"><div class="slot-row"><select id="slot2" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 2 --</option></select><input type="text" id="slot2_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)"></div><div class="row g-1"><div class="col-6"><input type="text" id="slot2_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia"></div><div class="col-6"><input type="text" id="slot2_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente"></div></div></div>
                                <div class="slot-container"><div class="slot-row"><select id="slot3" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 3 --</option></select><input type="text" id="slot3_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)"></div><div class="row g-1"><div class="col-6"><input type="text" id="slot3_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia"></div><div class="col-6"><input type="text" id="slot3_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente"></div></div></div>
                                <div class="slot-container"><div class="slot-row"><select id="slot4" class="form-select form-control-custom form-select-sm"><option value="">-- Antimicrobiano 4 --</option></select><input type="text" id="slot4_d" class="form-control form-control-custom form-control-sm dia-input" placeholder="Dia (D1)"></div><div class="row g-1"><div class="col-6"><input type="text" id="slot4_poso" class="form-control form-control-custom form-control-sm" placeholder="Posologia"></div><div class="col-6"><input type="text" id="slot4_dil" class="form-control form-control-custom form-control-sm" placeholder="Diluente"></div></div></div>
                                <div class="mt-3 pt-2 border-top">
                                    <label class="form-label-custom text-secondary"><i class="bi bi-capsule me-1"></i> Demais Medicamentos da Prescrição</label>
                                    <textarea id="outrosMedicamentos" class="form-control form-control-custom" rows="2" placeholder="Demais medicamentos..."></textarea>
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-7 position-relative">
                            <button class="btn btn-sm btn-outline-secondary position-absolute top-0 end-0 m-2 fw-bold" style="z-index: 10;" onclick="copiarSoap()"><i class="bi bi-copy"></i> Copiar SOAP</button>
                            <textarea id="parecerSoap" class="soap-output pt-5" readonly placeholder="Aguardando dados clínicos..."></textarea>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
<script>
$(document).ready(function() { $('#comorbidadesSelect').select2({ placeholder: "Selecione...", allowClear: true, width: '100%' }); });
function addComorbidade(tag) { let select = $('#comorbidadesSelect'); let vals = select.val() || []; if (!vals.includes(tag)) { vals.push(tag); select.val(vals).trigger('change'); } }
function updateFileName(input) { const display = document.getElementById('fileNameDisplay'); display.innerText = (input.files && input.files.length > 0) ? input.files[0].name : "Nenhum arquivo escolhido"; }
async function fazerLogin() {
    const user = document.getElementById('user').value.trim().toLowerCase();
    const pass = document.getElementById('pass').value.trim();
    if ((user === 'noberto' || user === 'admin') && (pass === 'admin123' || pass === 'admin')) {
        document.getElementById('login-view').classList.add('d-none'); document.getElementById('app-view').classList.remove('d-none'); carregarCatalogo(); return;
    }
    document.getElementById('loginError').classList.remove('d-none');
}
function fazerLogout() { document.getElementById('app-view').classList.add('d-none'); document.getElementById('login-view').classList.remove('d-none'); document.getElementById('user').value=''; document.getElementById('pass').value=''; }
function novaTriagem() { location.reload(); }
async function carregarCatalogo() {
    const res = await fetch("/api/antimicrobianos"); const catalogo = await res.json();
    ['slot1', 'slot2', 'slot3', 'slot4'].forEach(id => {
        const select = document.getElementById(id); select.innerHTML = `<option value="">-- Antimicrobiano --</option>`;
        catalogo.forEach(item => { const opt = document.createElement("option"); opt.value = item.nome; opt.innerText = item.nome; select.appendChild(opt); });
    });
}
async function extrairPdf() {
    const fileInput = document.getElementById("pdfFile"); const textoManualInput = document.getElementById("textoManual").value;
    let formData = new FormData();
    if (fileInput.files[0]) formData.append("file", fileInput.files[0]);
    else if (textoManualInput.trim() !== "") formData.append("texto", textoManualInput);
    else return alert("Selecione PDF ou cole texto.");
    const res = await fetch("/api/extrair-pdf", { method: "POST", body: formData }); const data = await res.json();
    document.getElementById("textoBrutoOculto").value = data.texto_anonimizado;
    document.getElementById("outrosMedicamentos").value = data.outros_meds.join(", ");
    const slots = ["slot1", "slot2", "slot3", "slot4"];
    slots.forEach(id => { document.getElementById(id).value = ""; document.getElementById(id+"_d").value = ""; document.getElementById(id+"_poso").value = ""; document.getElementById(id+"_dil").value = ""; });
    for (let i = 0; i < data.atbs.length && i < 4; i++) {
        document.getElementById(slots[i]).value = data.atbs[i].nome; document.getElementById(slots[i]+"_d").value = data.atbs[i].dia || "";
        document.getElementById(slots[i]+"_poso").value = data.atbs[i].poso || ""; document.getElementById(slots[i]+"_dil").value = data.atbs[i].diluente || "";
    }
    const st = document.getElementById("statusExtracao"); st.innerText = `Extraído: ${data.atbs.length} atb(s).`; st.classList.remove("d-none");
}
async function gerarAnalise() {
    const comorbs = $('#comorbidadesSelect').val() || []; const atbs = [];
    ['slot1', 'slot2', 'slot3', 'slot4'].forEach(id => {
        const nome = document.getElementById(id).value;
        if(nome) atbs.push({ nome: nome, dia: document.getElementById(id+'_d').value, poso: document.getElementById(id+'_poso').value, diluente: document.getElementById(id+'_dil').value });
    });
    const payload = {
        sexo: document.getElementById("sexo").value, idade: parseInt(document.getElementById("idade").value) || 0,
        peso: parseFloat(document.getElementById("peso").value) || 0, altura: parseFloat(document.getElementById("altura").value) || 0,
        creatinina: parseFloat(document.getElementById("creatinina").value) || 0, comorbidades: comorbs, antimicrobianos: atbs,
        outros_medicamentos_texto: document.getElementById("outrosMedicamentos").value,
        texto_prescricao_bruto: document.getElementById("textoBrutoOculto").value + "\\n" + document.getElementById("textoManual").value
    };
    const res = await fetch("/api/avaliar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const data = await res.json();
    document.getElementById("valClcr").innerHTML = data.metricas.clcr + ' <span style="font-size:1rem;">mL/min</span>';
    document.getElementById("navClcr").innerText = data.metricas.clcr + " mL/min"; document.getElementById("navAlertas").innerText = data.alertas_count;
    document.getElementById("valPesoAdotado").innerText = data.metricas.peso_adotado; document.getElementById("parecerSoap").value = data.soap;
}
function copiarSoap() { const txt = document.getElementById("parecerSoap"); txt.select(); navigator.clipboard.writeText(txt.value); }
</script>
</body>
</html>
"""

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

@app.get("/", response_class=HTMLResponse)
def index(): return HTML_TEMPLATE

@app.post("/api/login")
def login(data: dict):
    if data.get("username", "").strip().lower() in ["noberto", "admin"] and data.get("password", "").strip() in ["admin123", "admin"]:
        return {"success": True, "role": "admin"}
    return {"success": False}

@app.get("/api/antimicrobianos")
def get_antimicrobianos():
    conn = sqlite3.connect("radar_clinico.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, nome_generico, nomes_comerciais FROM antimicrobianos ORDER BY nome_generico ASC")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "nome": f"{r[1]} ({r[2]})" if r[2] else r[1], "nome_generico": r[1]} for r in rows]

@app.post("/api/extrair-pdf")
async def processar_pdf(file: Optional[UploadFile] = File(None), texto: Optional[str] = Form(None)):
    texto_bruto = ""
    if file:
        reader = pypdf.PdfReader(file.file)
        texto_bruto = "\n".join([(p.extract_text() or "") for p in reader.pages])
    elif texto: texto_bruto = texto
    texto_anon = limpar_texto_prescricao(texto_bruto)
    linhas_validas = [l.strip() for l in texto_anon.splitlines() if l.strip() and not any(n in sem_acentos(l.lower()) for n in ["suspender", "alergia"])]
    texto_limpo_norm = sem_acentos(" ".join(linhas_validas).lower())
    
    conn = sqlite3.connect("radar_clinico.db")
    cursor = conn.cursor()
    cursor.execute("SELECT nome_generico, nomes_comerciais, diluente_padrao FROM antimicrobianos")
    atbs_db = cursor.fetchall()
    conn.close()
    
    atbs_encontrados, genes_ja_incluidos = [], set()
    for idx, linha in enumerate(linhas_validas):
        linha_norm = sem_acentos(linha.lower())
        bloco_contexto = " ".join(linhas_validas[idx:idx+3])
        for gen, com, dil_padrao in atbs_db:
            if gen in genes_ja_incluidos: continue
            termos = [sem_acentos(gen.lower())] + ([sem_acentos(c.strip().lower()) for c in com.split(",")] if com else [])
            if any(t and re.search(r'\b' + re.escape(t) + r'\b', linha_norm) for t in termos):
                genes_ja_incluidos.add(gen)
                det = extrair_detalhes_linha(bloco_contexto)
                atbs_encontrados.append({"nome": f"{gen} ({com})" if com else gen, "dia": det["dia"], "poso": det["poso"], "diluente": det["diluente"] or dil_padrao})

    dicionario_comuns = ["dipirona", "paracetamol", "tramadol", "morfina", "fentanil", "omeprazol", "pantoprazol", "esomeprazol", "ondansetrona", "bromoprida", "metoclopramida", "enoxaparina", "heparina", "rivaroxabana", "apixabana", "varfarina", "clopidogrel", "furosemida", "espironolactona", "losartana", "enalapril", "anlodipino", "nifedipino", "metoprolol", "carvedilol", "amiodarona", "sinvastatina", "insulina", "metformina", "hidrocortisona", "dexametasona", "prednisona", "fenitoina", "acido valproico", "levetiracetam", "haloperidol", "quetiapina", "diazepam", "midazolam", "escitalopram", "sertralina", "salbutamol", "noradrenalina", "dobutamina"]
    comuns_encontrados = [med.title() for med in dicionario_comuns if re.search(r'\b' + re.escape(med) + r'\b', texto_limpo_norm)]
    return {"texto_anonimizado": texto_anon, "atbs": atbs_encontrados, "outros_meds": comuns_encontrados}

def extrair_mg_da_posologia(posologia: str) -> float:
    if not posologia: return 0.0
    poso_norm = posologia.lower().replace(".", "").replace(",", ".")
    m = re.search(r'(\d+(?:\.\d+)?)\s*(mg|g|ui)', poso_norm)
    if not m: return 0.0
    dose = float(m.group(1)) * (1000.0 if m.group(2) == 'g' else 1.0)
    mult = 4.0 if re.search(r'(6/6|6h)', poso_norm) else (3.0 if re.search(r'(8/8|8h)', poso_norm) else (2.0 if re.search(r'(12/12|12h)', poso_norm) else 1.0))
    return dose * mult

@app.post("/api/avaliar")
def avaliar_paciente(payload: AvaliacaoPayload):
    metricas = calcular_metricas(payload.sexo, payload.idade, payload.peso, payload.altura, payload.creatinina)
    clcr = metricas["clcr"]
    texto_bruto_norm = sem_acentos(payload.texto_prescricao_bruto.lower())
    alertas_count, conn = 0, sqlite3.connect("radar_clinico.db")
    cursor = conn.cursor()
    avaliacoes, farmacotecnias, incompatibilidades_encontradas = [], [], set()
    
    for atb in payload.antimicrobianos:
        nome_generico = atb.nome.split(" (")[0]
        cursor.execute("SELECT * FROM antimicrobianos WHERE nome_generico = ?", (nome_generico,))
        row = cursor.fetchone()
        if row:
            limite = row[4] if clcr >= 50 else (row[5] if clcr >= 30 else (row[6] if clcr >= 10 else row[7]))
            dil_recomendado, monit, farm_info = row[8], row[9], row[10]
            dose_dig = extrair_mg_da_posologia(atb.poso)
            status = f"Pendente posologia (Teto ClCr {clcr}: {limite}mg/dia)" if dose_dig == 0 else (f"ALERTA [!]: SOBREDOSE ({int(dose_dig)}mg/dia > {limite}mg/dia)." if dose_dig > limite else f"Posologia ADEQUADA ({int(dose_dig)}mg/dia <= {limite}mg/dia).")
            if "ALERTA" in status: alertas_count += 1

            alerta_dil = ""
            if (atb.diluente or "").strip():
                cursor.execute("SELECT condicao, alerta FROM regras_farmacotecnicas WHERE LOWER(farmaco) = LOWER(?)", (sem_acentos(nome_generico.lower()),))
                for cond_r, msg_a in cursor.fetchall():
                    if cond_r.lower() in sem_acentos(atb.diluente.lower()):
                        alerta_dil = f" | [INCOMPATIBILIDADE: {msg_a}]"
                        incompatibilidades_encontradas.add(f"[ALERTA FARMACOTÉCNICO] {nome_generico.upper()}: {msg_a}")

            avaliacoes.append(f"       * {atb.nome} [{atb.poso or 'S/ Poso'}] | Diluente: {atb.diluente or dil_recomendado} -> {status}{alerta_dil}")
            farmacotecnias.append(f"• {nome_generico} (Monitorar: {monit}): {farm_info}")

    riscos_comorbidade = set()
    if payload.comorbidades:
        cursor.execute("SELECT comorbidade, farmaco_contraindicado, alerta FROM comorbidades_risco")
        contexto_meds = " ".join([sem_acentos(a.nome.lower()) for a in payload.antimicrobianos]) + " " + sem_acentos(payload.outros_medicamentos_texto.lower()) + " " + texto_bruto_norm
        for c_regra, f_regra, a_regra in cursor.fetchall():
            if any(sem_acentos(c_regra.lower()) == sem_acentos(d.lower()) for d in payload.comorbidades) and sem_acentos(f_regra.lower()) in contexto_meds:
                riscos_comorbidade.add(f"[RISCO - {c_regra.upper()}] {f_regra}: {a_regra}")
                alertas_count += 1

    conn.close()
    meds_gerais = sem_acentos(payload.outros_medicamentos_texto.lower()) + " " + texto_bruto_norm
    tem_heparina = any(h in meds_gerais for h in ["heparina", "enoxaparina", "versan", "clexane"])
    tem_ibp = any(i in meds_gerais for i in ["omeprazol", "pantoprazol", "esomeprazol"])
    alerta_tev = "ALERTA [!]: Paciente de risco SEM profilaxia." if (not tem_heparina and (payload.idade >= 60 or "Acamado" in payload.comorbidades)) else "Conforme."
    if "ALERTA" in alerta_tev: alertas_count += 1
    alerta_lamg = "ALERTA [!]: IBP ativo. Reavaliar indicação." if tem_ibp else "Conforme."
    if "ALERTA" in alerta_lamg: alertas_count += 1

    soap = [
        "=== EVOLUÇÃO FARMACÊUTICA // RADAR CLÍNICO ===",
        f"[O] Idade: {payload.idade}a | Sexo: {payload.sexo.upper()} | Peso: {payload.peso}kg (Adotado: {metricas['peso_adotado']}kg) | ClCr: {clcr} mL/min",
        f"    Comorbidades: {', '.join(payload.comorbidades) if payload.comorbidades else 'Nenhuma'}",
        f"    Outros Medicamentos: {payload.outros_medicamentos_texto or 'Nenhum'}",
        "[A] AVALIAÇÃO FARMACÊUTICA:",
        "    1. Antimicrobianos:"
    ] + (avaliacoes if avaliacoes else ["       * Nenhum antimicrobiano selecionado."]) + [
        f"    2. Profilaxias: TEV: {alerta_tev} | LAMG: {alerta_lamg}"
    ]
    if riscos_comorbidade: soap += ["    3. Alertas por Comorbidades:"] + [f"       * {r}" for r in riscos_comorbidade]
    if incompatibilidades_encontradas: soap += ["    4. Incompatibilidades e Diluentes:"] + [f"       * {i}" for i in incompatibilidades_encontradas]
    if farmacotecnias: soap += ["[P] ORIENTAÇÕES DE PREPARO E MONITORIZAÇÃO:"] + [f"    {f}" for f in farmacotecnias]

    return {"metricas": metricas, "soap": "\n".join(soap), "alertas_count": alertas_count}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
