import sqlite3
import os

def setup_database():
    if os.path.exists("radar_clinico.db"):
        os.remove("radar_clinico.db")
        print("Base de dados antiga removida. Criando uma nova...")

    conn = sqlite3.connect("radar_clinico.db")
    cursor = conn.cursor()
    
    # 1. Usuários (Credenciais: Noberto / admin123)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO usuarios (username, password, role) VALUES ('Noberto', 'admin123', 'admin')")

    # 2. Catálogo Completo de Antimicrobianos Hospitalares
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS antimicrobianos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_generico TEXT UNIQUE NOT NULL,
            nomes_comerciais TEXT,
            indicacao TEXT,
            dose_max_padrao_mg INTEGER,
            dose_max_clcr30_50_mg INTEGER,
            dose_max_clcr10_30_mg INTEGER,
            dose_max_clcr10_mg INTEGER,
            diluente_padrao TEXT,
            monitorizacao TEXT,
            farmacotecnia TEXT
        )
    """)

    atbs = [
        # Cefalosporinas
        ("Cefazolina", "Kefazol, Cezolin", "Profilaxia Cirúrgica / Pele / ITU", 6000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, sinais de flebite", "Reconstituir em 10mL AD. Diluir em 50-100mL SF 0,9% ou SG 5% (infusão 30-60 min) ou EV direto lento (3-5 min)."),
        ("Ceftriaxona", "Rocefin, Triaxin", "Infecções Gerais / Meningite", 4000, 4000, 2000, 2000, "SF 0,9% ou SG 5% (50-100mL)", "Lama biliar, função hepática", "PROIBIDO diluir ou correr em Y com soluções contendo Cálcio (Ringer Lactato). Infusão em 30 min."),
        ("Cefepima", "Maxcef, Maxefime", "Infecções Graves / Neutropenia", 6000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Neurotoxicidade (mioclonias, confusão em DRC)", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 30 min (ou estendida em 3-4h)."),
        ("Ceftazidima", "Fortaz, Kefadim", "Pseudomonas / Infecções Graves", 6000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, risco neurotóxico em DRC", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 30 min."),
        ("Ceftazidima + Avibactam", "Zavicefta", "Bactérias MDR / KPC", 7500, 3750, 1875, 937, "SF 0,9% ou SG 5% (50-100mL)", "Função renal rigorosa, teste de Coombs", "Diluir em 50-250mL SF 0,9% ou SG 5%. Infusão obrigatória em 2 horas."),
        ("Cefuroxima", "Zinacef, Zinnat", " Infecções Respiratórias / Pele", 4500, 3000, 1500, 750, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, função hepática", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 30 min."),
        ("Cefalexina", "Keflex", "Infecções Leves (VO)", 4000, 3000, 1500, 1000, "Via Oral (Água)", "Função renal", "Uso exclusivo Via Oral."),

        # Penicilinas e Inibidores de Beta-Lactamase
        ("Piperacilina + Tazobactam", "Tazocin", "Infecções Graves / Nosocomiais", 18000, 13500, 9000, 6750, "SF 0,9% ou SG 5% (50-100mL)", "Creatinina (sinergismo c/ Vanco), Na+, plaquetas", "Reconstituir c/ 20mL SF/AD. Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão estendida (3-4h) recomendada. Incompatível c/ Ringer Lactato."),
        ("Ampicilina", "Binotal, Amplacilina", "Enterococcus / Listeria", 12000, 6000, 4000, 2000, "Exclusivo SF 0,9% (50-100mL)", "Função renal, rash cutâneo", "INCOMPATÍVEL com SG 5% (hidrólise rápida). Diluir exclusivamente em SF 0,9% e infundir em até 1h após preparo."),
        ("Ampicilina + Sulbactam", "Unasyn", "Acinetobacter / Intra-abdominal", 12000, 6000, 3000, 1500, "Exclusivo SF 0,9% (50-100mL)", "Função renal, transaminases", "Baixa estabilidade em SG 5%. Diluir preferencialmente em 50-100mL de SF 0,9%. Infusão em 30 min."),
        ("Amoxicilina + Clavulanato", "Clavulin", "Respiratório / Comunitárias", 3600, 2400, 1200, 1200, "Exclusivo SF 0,9% (50-100mL)", "Função hepática, diarreia", "Apresentação EV é INCOMPATÍVEL com SG 5% e bicarbonato. Diluir exclusivamente em SF 0,9% e infundir em 30-40 min (estabilidade máxima 20 min após diluição)."),
        ("Oxacilina", "Staficilin-N", "Staphylococcus aureus (MSSA)", 12000, 12000, 12000, 12000, "SF 0,9% ou SG 5% (50-100mL)", "Hepatotoxicidade, nefrite intersticial, flebite", "Sem ajuste renal obrigatório, mas alto risco de flebite. Diluir em 50-100mL SF 0,9% ou SG 5% e infundir em 30-60 min."),

        # Carbapenêmicos e Monobactâmicos
        ("Meropenem", "Meronem", "Infecções Graves / ESBL", 6000, 2000, 1000, 500, "SF 0,9% (100mL)", "Função renal, limiar convulsivo", "Diluir em 100mL SF 0,9% (maior estabilidade que SG 5%). Infusão em 30 min ou estendida em 3h."),
        ("Imipenem + Cilastatina", "Tienam", "Infecções Polimicrobianas / MDR", 4000, 1500, 1000, 500, "SF 0,9% (100mL)", "Alto risco convulsivo em DRC ou lesão de SNC", "Diluir em 100mL SF 0,9%. Doses <=500mg correr em 30 min; doses >500mg correr em 60 min."),
        ("Ertapenem", "Invanz", "ESBL Comunitário (1x/dia)", 1000, 1000, 500, 500, "Exclusivo SF 0,9% (50mL)", "Função renal, neurotoxicidade em idosos", "PROIBIDO diluir em SG 5%. Reconstituir c/ 10mL AD/SF e diluir exclusivamente em 50mL SF 0,9%. Infundir em 30 min."),
        ("Aztreonam", "Azactam", "Gram-negativos (Alérgicos a Beta-lactâmicos)", 8000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, transaminases", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 20-60 min."),

        # Glicopeptídeos, Lipopeptídeos e Oxazolidinonas
        ("Vancomicina", "Vancocina", "MRSA / Gram-positivos", 4000, 1500, 1000, 500, "SF 0,9% ou SG 5% (200-250mL)", "Vancocinemia (vale 15-20), creatinina diária, Síndrome do Homem Vermelho", "Concentração máxima 5mg/mL (1g em min 200mL; 500mg em min 100mL). Infusão lenta obrigatória (>=60 min para 1g)."),
        ("Teicoplanina", "Targocid", "MRSA / Infecções Ósseas", 800, 400, 200, 200, "SF 0,9% ou SG 5% (50-100mL)", "Função renal (ajustar após D4), plaquetas", "Reconstituir lentamente rolando o frasco para não espumar. Diluir em 50-100mL SF 0,9% ou SG 5% e correr em 30 min."),
        ("Daptomicina", "Cubicin", "MRSA / VRE (Bacteremia/Endocardite)", 1000, 1000, 500, 500, "Exclusivo SF 0,9% (50-100mL)", "CPK semanal (rabdomiólise), função renal (48/48h se ClCr<30)", "INCOMPATÍVEL com Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9% (ou Ringer Lactato). Infundir em 30 min. Inativada pelo surfactante pulmonar (não usar p/ pneumonia)."),
        ("Linezolida", "Zyvox", "MRSA / VRE (Pneumonia/Pele)", 1200, 1200, 1200, 1200, "Bolsa Pronta (300mL)", "Plaquetopenia (>10-14 dias), risco síndrome serotoninérgica", "Sem ajuste renal. Bolsa pronta para uso (proteger da luz). Infundir em 30 a 120 min. Não conectar em série."),

        # Polimixinas e Aminoglicosídeos
        ("Polimixina B", "Bedfordpoly-B", "Gram-negativos MDR (KPC/Acineto)", 2500000, 2500000, 2500000, 2500000, "Exclusivo SG 5% (300-500mL)", "Nefrotoxicidade, neurotoxicidade (parestesias)", "Não requer ajuste renal (excreção não-renal). Diluir EXCLUSIVAMENTE em 300 a 500mL de SG 5%. Infusão lenta em 60 a 120 min."),
        ("Colistina", "Colis-Tek (Polimixina E)", "Gram-negativos MDR / ITU", 360, 220, 130, 100, "SF 0,9% ou SG 5% (50-100mL)", "Nefrotoxicidade severa, neurotoxicidade", "Exige ajuste renal rigoroso. Diluir em 50-100mL SF 0,9% ou SG 5% e infundir em 30-60 min."),
        ("Amicacina", "Novamin", "Gram-negativos / Micobactérias", 1500, 750, 500, 250, "SF 0,9% ou SG 5% (100-200mL)", "Nefrotoxicidade, ototoxicidade irreversível", "Dose única diária preferencial. Diluir em 100-200mL SF 0,9% ou SG 5% e infundir em 30-60 min. Não misturar com beta-lactâmicos na mesma via."),
        ("Gentamicina", "Garamicina", "Sinergismo Endocardite / Gram-negativos", 500, 300, 160, 80, "SF 0,9% ou SG 5% (50-100mL)", "Nefrotoxicidade, ototoxicidade vestibular", "Diluir em 50-100mL SF 0,9% ou SG 5% e infundir em 30-60 min."),

        # Quinolonas, Macrolídeos, Glicilciclinas e Outros
        ("Ciprofloxacino", "Cipro", "ITU / Intra-abdominal / Pseudomonas", 1200, 800, 400, 400, "Bolsa Pronta (100-200mL)", "Intervalo QTc, tendinite, confusão em idosos", "Bolsa pronta para uso. Infundir em 60 min em veia calibrosa para evitar flebite. Fotossensível."),
        ("Levofloxacino", "Tavanic, Levaquin", "Pneumonia Comunitária / ITU", 750, 500, 250, 250, "Bolsa Pronta (100-150mL)", "Intervalo QTc, disglicemia, delírio em idosos", "Bolsa pronta para uso. Infundir lentamente em 60 a 90 min (risco de hipotensão se infusão rápida)."),
        ("Metronidazol", "Flagyl", "Anaeróbios / Clostridioides difficile", 2000, 2000, 1500, 1000, "Bolsa Pronta (100mL)", "Neuropatia periférica, efeito dissulfiram", "Bolsa pronta de 500mg/100mL. Infundir em 30-60 min. Não refrigerar (risco de precipitação)."),
        ("Clindamicina", "Dalacin C", "Anaeróbios / Pele / Toxina estreptocócica", 2700, 2700, 2700, 2700, "SF 0,9% ou SG 5% (50-100mL)", "Diarreia / Colite pseudomembranosa", "Sem ajuste renal. PROIBIDO fazer em bolus EV direto (risco de parada cardíaca). Concentração máx 18mg/mL; infundir em 20-60 min."),
        ("Tigeciclina", "Tygacil", "MDR Intra-abdominal / Pele (Exceto Pseudomonas)", 200, 200, 200, 200, "SF 0,9% ou SG 5% (100mL)", "Hepatopatia grave (reduzir manutenção p/ 25mg 12/12h), náuseas, pancreatite", "Sem ajuste renal. Ajustar na insuficiência hepática Child-Pugh C. Diluir em 100mL SF 0,9% ou SG 5% e correr em 30-60 min."),
        ("Sulfametoxazol + Trimetoprima", "Bactrim", "Pneumocistose / Stenotrophomonas", 3200, 1600, 800, 400, "Exclusivo SG 5% (125mL por ampola)", "Hipercalemia, insuficiência renal, mielossupressão", "Cada ampola (5mL) exige diluição em 125mL de SG 5% (em restrição hídrica, mínimo 75mL SG 5%). Estabilidade curta após diluição (2-4h). Infundir em 60-90 min."),
        ("Azitromicina", "Zitromax", "Pneumonia Atípica", 500, 500, 500, 500, "SF 0,9% ou SG 5% (250-500mL)", "Prolongamento QTc, função hepática", "Sem ajuste renal. Diluir 500mg em 250mL (correr em 60 min) ou 500mL (correr em 3h). Nunca fazer em bolus."),
        ("Claritromicina", "Klaricid", "Pneumonia / Micobactérias", 1000, 500, 500, 250, "SF 0,9% ou SG 5% (250mL)", "Prolongamento QTc, fortes interações CYP3A4, flebite", "Reconstituir APENAS com 10mL de Água Destilada (proibido reconstituir com SF). Diluir em 250mL SF 0,9% ou SG 5% e infundir em 60 min."),

        # Antifúngicos e Antivirais
        ("Fluconazol", "Zoltec", "Candidíase / Criptococose", 800, 400, 200, 200, "Bolsa Pronta (100mL)", "Função hepática, intervalo QTc, ajuste renal (50% se ClCr<=50)", "Bolsa pronta (200mg/100mL). Infundir em 60 min."),
        ("Anfotericina B Desoxicolato", "Fungizon", "Micoses Sistêmicas Graves", 100, 100, 100, 100, "Exclusivo SG 5% (500mL)", "Nefrotoxicidade grave, hipocalemia, hipomagnesemia, febre/calafrios", "PROIBIDO diluir em SF 0,9% (precipita imediatamente). Reconstituir em AD e diluir exclusivamente em SG 5% (concentração <=0,1mg/mL). Infundir em 4 a 6 horas."),
        ("Anfotericina B Lipossomal", "Ambisome", "Fúngicas Invasivas / Leishmaniose", 400, 400, 400, 400, "Exclusivo SG 5% (250-500mL)", "Eletrólitos (K+, Mg2+), creatinina", "INCOMPATÍVEL com SF 0,9%. Reconstituir com 12mL AD, agitar vigorosamente por 30s e diluir exclusivamente em SG 5% usando filtro de 5 micra. Infundir em 2h."),
        ("Aciclovir", "Zovirax", "Herpes Simples / Encefalite / Zoster", 3000, 2000, 1000, 500, "SF 0,9% ou SG 5% (100mL)", "Nefrotoxicidade por cristalúria (manter hidratação), neurotoxicidade", "Diluir em 100mL SF 0,9% ou SG 5% (concentração máx 7mg/mL). Infusão obrigatória em no mínimo 60 min.")
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO antimicrobianos 
        (nome_generico, nomes_comerciais, indicacao, dose_max_padrao_mg, dose_max_clcr30_50_mg, dose_max_clcr10_30_mg, dose_max_clcr10_mg, diluente_padrao, monitorizacao, farmacotecnia) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, atbs)

    # 3. Interações Medicamentosas Relevantes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            droga_a TEXT NOT NULL,
            droga_b TEXT NOT NULL,
            gravidade TEXT,
            mecanismo TEXT,
            conduta TEXT
        )
    """)
    interacoes = [
        ("Vancomicina", "Piperacilina + Tazobactam", "Grave", "Potencialização de nefrotoxicidade aguda sinérgica", "Monitorar creatinina e débito urinário diariamente; considerar substituir por Cefepima ou Meropenem se indicado."),
        ("Vancomicina", "Amicacina", "Grave", "Nefrotoxicidade e ototoxicidade aditivas/sinérgicas", "Monitorar creatinina diária e níveis séricos (vancocinemia)."),
        ("Vancomicina", "Furosemida", "Moderada", "Aumento do risco de nefrotoxicidade e ototoxicidade", "Monitorar função renal e balanço hídrico."),
        ("Ceftriaxona", "Ringer Lactato", "Contraindicada", "Precipitação intravascular fatal de ceftriaxona-cálcio", "Suspender diluição ou infusão simultânea com soluções contendo cálcio."),
        ("Meropenem", "Ácido Valproico", "Grave", "Redução drástica (60-100%) dos níveis séricos de valproato em 24h (risco de convulsão)", "Associar ou substituir o anticonvulsivante (ex: Levetiracetam ou Fenitoína)."),
        ("Ciprofloxacino", "Amiodarona", "Maior", "Prolongamento sinérgico do intervalo QTc (risco de Torsades de Pointes)", "Monitorização eletrocardiográfica e de K+/Mg2+; avaliar alternativa antimicrobiana."),
        ("Levofloxacino", "Amiodarona", "Maior", "Prolongamento sinérgico do intervalo QTc", "Monitorar ECG e eletrólitos."),
        ("Fluconazol", "Amiodarona", "Maior", "Inibição do metabolismo da amiodarona + prolongamento QTc", "Monitorar ECG; avaliar equinocandina se aplicável."),
        ("Linezolida", "Fentanil", "Maior", "Risco de Síndrome Serotoninérgica (inibição da MAO pela linezolida)", "Vigiar hipertermia, clônus, agitação e taquicardia."),
        ("Linezolida", "Escitalopram", "Contraindicada", "Alto risco de Síndrome Serotoninérgica", "Suspender ISRS ou substituir Linezolida (ex: Vancomicina/Daptomicina)."),
        ("Omeprazol", "Clopidogrel", "Moderada", "Inibição competitiva da CYP2C19 reduzindo conversão ativa do clopidogrel", "Substituir Omeprazol por Pantoprazol caso haja indicação formal de IBP.")
    ]
    cursor.executemany("INSERT OR IGNORE INTO interacoes (droga_a, droga_b, gravidade, mecanismo, conduta) VALUES (?, ?, ?, ?, ?)", interacoes)

    # 4. Regras Farmacotécnicas e de Diluição (Análise de Contexto de Linha)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regras_farmacotecnicas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmaco TEXT NOT NULL,
            condicao TEXT NOT NULL,
            alerta TEXT NOT NULL
        )
    """)
    regras_farmaco = [
        ("dipirona", "ad", "Diluir Dipirona em Água Destilada (AD) ou bolus rápido aumenta risco de dor, flebite e hipotensão. Prefira diluir em SF 0,9% ou SG 5%."),
        ("dipirona", "agua destilada", "Diluir Dipirona em Água Destilada (AD) aumenta risco de dor e flebite. Prefira SF 0,9% ou SG 5%."),
        ("fenitoina", "sg", "INCOMPATÍVEL com Soro Glicosado (SG 5%) por precipitação de cristais. Diluir exclusivamente em SF 0,9%."),
        ("fenitoina", "glicosado", "INCOMPATÍVEL com Soro Glicosado (SG 5%) por precipitação. Utilizar exclusivamente SF 0,9%."),
        ("ampicilina", "sg", "Incompatível/baixa estabilidade em Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("ampicilina", "glicosado", "Incompatível/baixa estabilidade em Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("clavulin", "sg", "Amoxicilina+Clavulanato EV é incompatível com SG 5%. Diluir exclusivamente em SF 0,9%."),
        ("amoxicilina", "sg", "Amoxicilina+Clavulanato EV é incompatível com SG 5%. Diluir exclusivamente em SF 0,9%."),
        ("ertapenem", "sg", "PROIBIDO diluir Ertapenem em Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("invanz", "sg", "PROIBIDO diluir Ertapenem em Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("daptomicina", "sg", "INCOMPATÍVEL com Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9% ou Ringer Lactato."),
        ("cubicin", "sg", "INCOMPATÍVEL com Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("polimixina", "sf", "Polimixina B apresenta baixa estabilidade em SF 0,9%. Diluir exclusivamente em 300-500mL de SG 5%."),
        ("bactrim", "sf", "Sulfametoxazol+Trimetoprima EV tem menor estabilidade em SF 0,9% (risco de precipitação). Diluir em SG 5% (125mL por ampola)."),
        ("sulfametoxazol", "sf", "Sulfametoxazol+Trimetoprima EV deve ser diluído preferencialmente em SG 5% (125mL por ampola)."),
        ("anfotericina", "sf", "PROIBIDO diluir Anfotericina B em SF 0,9% (precipitação imediata). Diluir exclusivamente em SG 5%."),
        ("noradrenalina", "sf", "Noradrenalina em SF 0,9% puro sofre oxidação mais rápida. Diluir preferencialmente em SG 5%."),
        ("amiodarona", "sf", "Amiodarona é menos estável em SF 0,9% para infusão contínua. Diluir exclusivamente em SG 5% (frasco ecoflac/vidro)."),
        ("ceftriaxona", "ringer", "CONTRAINDICADO: Ceftriaxona precipita com o cálcio do Ringer Lactato. Diluir em SF 0,9% ou SG 5%."),
        ("rocefin", "ringer", "CONTRAINDICADO: Ceftriaxona precipita com o cálcio do Ringer Lactato. Diluir em SF 0,9% ou SG 5%."),
        ("tazocin", "ringer", "Piperacilina+Tazobactam (fórmula sem EDTA) é incompatível com Ringer Lactato. Diluir em SF 0,9% ou SG 5%."),
        ("omeprazol", "sonda", "Omeprazol cápsula com microgrânulos gastro-resistentes não deve ser triturado em sonda enteral (obstrução e inativação ácida)."),
        ("nifedipino", "sonda", "Medicamento de liberação prolongada (Retard/Oros): PROIBIDO triturar para sonda (risco de hipotensão severa e reflexo simpático).")
    ]
    cursor.executemany("INSERT OR IGNORE INTO regras_farmacotecnicas (farmaco, condicao, alerta) VALUES (?, ?, ?)", regras_farmaco)

    # 5. Comorbidades e Riscos Clínicos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comorbidades_risco (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comorbidade TEXT NOT NULL,
            farmaco_contraindicado TEXT NOT NULL,
            alerta TEXT NOT NULL
        )
    """)
    comorbidades = [
        ("Hepatopatia", "Tigeciclina", "Em hepatopatas graves (Child-Pugh C), reduzir dose de manutenção para 25mg 12/12h após ataque de 100mg."),
        ("Hepatopatia", "Ceftriaxona", "Risco de colestase/pseudolitíase biliar; se associada a disfunção renal concomitante, não exceder 2g/dia."),
        ("Hepatopatia", "Fluconazol", "Risco de hepatotoxicidade medicamentosa; monitorar transaminases e bilirrubinas."),
        ("Hepatopatia", "Paracetamol", "Limitar dose máxima a 2g/dia em hepatopatas ou evitar uso regular."),
        ("DRC", "Nitrofurantoína", "Contraindicado em ClCr < 30 mL/min (concentração urinária ineficaz e risco de neuropatia/toxicidade pulmonar)."),
        ("DRC", "Amicacina", "Alto risco nefrotóxico em DRC; considerar alternativa menos nefrotóxica ou espaçar intervalo rigorosamente."),
        ("DRC", "Vancomicina", "Ajustar dose pelo ClCr e monitorar vancocinemia antes da 4ª dose."),
        ("Demência", "Ciprofloxacino", "Quinolonas reduzem limiar convulsivo e agravam delirium/confusão aguda em idosos com demência."),
        ("Demência", "Levofloxacino", "Quinolonas aumentam risco de delirium e agitação em idosos com declínio cognitivo."),
        ("Parkinson", "Metoclopramida", "CONTRAINDICADO na Doença de Parkinson (antagonismo dopaminérgico central agrava sintomas motores). Substituir por Ondansetrona."),
        ("Parkinson", "Bromoprida", "CONTRAINDICADO na Doença de Parkinson (bloqueio dopaminérgico central). Substituir por Ondansetrona."),
        ("Parkinson", "Haloperidol", "Evitar na Doença de Parkinson por agravamento severo do parkinsonismo (preferir Quetiapina se necessário).")
    ]
    cursor.executemany("INSERT OR IGNORE INTO comorbidades_risco (comorbidade, farmaco_contraindicado, alerta) VALUES (?, ?, ?)", comorbidades)

    conn.commit()
    conn.close()
    print("Base de dados criada/atualizada com sucesso!")

if __name__ == "__main__":
    setup_database()
