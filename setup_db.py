import sqlite3

def setup_database():
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
    cursor.execute("INSERT OR REPLACE INTO usuarios (username, password, role) VALUES ('admin', 'admin', 'admin')")

    cursor.execute("DROP TABLE IF EXISTS antimicrobianos")
    cursor.execute("""
        CREATE TABLE antimicrobianos (
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
        ("Cefazolina", "Kefazol, Cezolin", "Profilaxia Cirúrgica / Pele / ITU", 6000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, sinais de flebite", "Reconstituir em 10mL AD. Diluir em 50-100mL SF 0,9% ou SG 5% (infusão 30-60 min) ou EV direto lento (3-5 min)."),
        ("Ceftriaxona", "Rocefin, Triaxin", "Infecções Gerais / Meningite", 4000, 4000, 2000, 2000, "SF 0,9% ou SG 5% (50-100mL)", "Lama biliar, função hepática", "PROIBIDO diluir ou correr em Y com soluções contendo Cálcio (Ringer Lactato). Infusão em 30 min."),
        ("Cefepima", "Maxcef, Maxefime", "Infecções Graves / Neutropenia", 6000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Neurotoxicidade (mioclonias, confusão em DRC)", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 30 min (ou estendida em 3-4h)."),
        ("Ceftazidima", "Fortaz, Kefadim", "Pseudomonas / Infecções Graves", 6000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, risco neurotóxico em DRC", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 30 min."),
        ("Ceftazidima + Avibactam", "Zavicefta", "Bactérias MDR / KPC", 7500, 3750, 1875, 937, "SF 0,9% ou SG 5% (50-100mL)", "Função renal rigorosa, teste de Coombs", "Diluir em 50-250mL SF 0,9% ou SG 5%. Infusão obrigatória em 2 horas."),
        ("Cefuroxima", "Zinacef, Zinnat", "Infecções Respiratórias / Pele", 4500, 3000, 1500, 750, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, função hepática", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 30 min."),
        ("Cefalexina", "Keflex", "Infecções Leves (VO)", 4000, 3000, 1500, 1000, "Via Oral (Água)", "Função renal", "Uso exclusivo Via Oral."),
        ("Piperacilina + Tazobactam", "Tazocin", "Infecções Graves / Nosocomiais", 18000, 13500, 9000, 6750, "SF 0,9% ou SG 5% (50-100mL)", "Creatinina (sinergismo c/ Vanco), Na+, plaquetas", "Reconstituir c/ 20mL SF/AD. Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão estendida (3-4h) recomendada. Incompatível c/ Ringer Lactato."),
        ("Ampicilina", "Binotal, Amplacilina", "Enterococcus / Listeria", 12000, 6000, 4000, 2000, "Exclusivo SF 0,9% (50-100mL)", "Função renal, rash cutâneo", "INCOMPATÍVEL com SG 5% (hidrólise rápida). Diluir exclusivamente em SF 0,9% e infundir em até 1h após preparo."),
        ("Ampicilina + Sulbactam", "Unasyn", "Acinetobacter / Intra-abdominal", 12000, 6000, 3000, 1500, "Exclusivo SF 0,9% (50-100mL)", "Função renal, transaminases", "Baixa estabilidade em SG 5%. Diluir preferencialmente em 50-100mL de SF 0,9%. Infusão em 30 min."),
        ("Amoxicilina + Clavulanato", "Clavulin", "Respiratório / Comunitárias", 3600, 2400, 1200, 1200, "Exclusivo SF 0,9% (50-100mL)", "Função hepática, diarreia", "Apresentação EV é INCOMPATÍVEL com SG 5%. Diluir exclusivamente em SF 0,9% e infundir em 30-40 min."),
        ("Oxacilina", "Staficilin-N", "Staphylococcus aureus (MSSA)", 12000, 12000, 12000, 12000, "SF 0,9% ou SG 5% (50-100mL)", "Hepatotoxicidade, nefrite intersticial, flebite", "Sem ajuste renal obrigatório, mas alto risco de flebite. Diluir em 50-100mL SF 0,9% ou SG 5% e infundir em 30-60 min."),
        ("Meropenem", "Meronem", "Infecções Graves / ESBL", 6000, 2000, 1000, 500, "SF 0,9% (100mL)", "Função renal, limiar convulsivo", "Diluir em 100mL SF 0,9%. Infusão em 30 min ou estendida em 3h."),
        ("Imipenem + Cilastatina", "Tienam", "Infecções Polimicrobianas / MDR", 4000, 1500, 1000, 500, "SF 0,9% (100mL)", "Alto risco convulsivo em DRC ou lesão de SNC", "Diluir em 100mL SF 0,9%. Correr em 30 a 60 min."),
        ("Ertapenem", "Invanz", "ESBL Comunitário (1x/dia)", 1000, 1000, 500, 500, "Exclusivo SF 0,9% (50mL)", "Função renal, neurotoxicidade em idosos", "PROIBIDO diluir em SG 5%. Diluir exclusivamente em 50mL SF 0,9% e infundir em 30 min."),
        ("Aztreonam", "Azactam", "Gram-negativos (Alérgicos a Beta-lactâmicos)", 8000, 4000, 2000, 1000, "SF 0,9% ou SG 5% (50-100mL)", "Função renal, transaminases", "Diluir em 50-100mL SF 0,9% ou SG 5%. Infusão em 20-60 min."),
        ("Vancomicina", "Vancocina", "MRSA / Gram-positivos", 4000, 1500, 1000, 500, "SF 0,9% ou SG 5% (200-250mL)", "Vancocinemia (vale 15-20), creatinina diária, Síndrome do Homem Vermelho", "Concentração máxima 5mg/mL (1g em min 200mL). Infusão lenta obrigatória (>=60 min para 1g)."),
        ("Teicoplanina", "Targocid", "MRSA / Infecções Ósseas", 800, 400, 200, 200, "SF 0,9% ou SG 5% (50-100mL)", "Função renal (ajustar após D4), plaquetas", "Reconstituir rolando o frasco devagar sem espumar. Diluir em 50-100mL SF 0,9% ou SG 5% e correr em 30 min."),
        ("Daptomicina", "Cubicin", "MRSA / VRE (Bacteremia/Endocardite)", 1000, 1000, 500, 500, "Exclusivo SF 0,9% (50-100mL)", "CPK semanal (rabdomiólise), função renal", "INCOMPATÍVEL com SG 5%. Diluir exclusivamente em SF 0,9%. Infundir em 30 min. Não usar para pneumonia."),
        ("Linezolida", "Zyvox", "MRSA / VRE (Pneumonia/Pele)", 1200, 1200, 1200, 1200, "Bolsa Pronta (300mL)", "Plaquetopenia (>10-14 dias), risco síndrome serotoninérgica", "Sem ajuste renal. Bolsa pronta para uso (proteger da luz). Infundir em 30 a 120 min."),
        ("Polimixina B", "Bedfordpoly-B", "Gram-negativos MDR", 2500000, 2500000, 2500000, 2500000, "Exclusivo SG 5% (300-500mL)", "Nefrotoxicidade, neurotoxicidade", "Não requer ajuste renal. Diluir EXCLUSIVAMENTE em 300 a 500mL de SG 5%. Infusão lenta em 60 a 120 min."),
        ("Colistina", "Colis-Tek", "Gram-negativos MDR / ITU", 360, 220, 130, 100, "SF 0,9% ou SG 5% (50-100mL)", "Nefrotoxicidade severa, neurotoxicidade", "Exige ajuste renal rigoroso. Diluir em 50-100mL SF 0,9% ou SG 5% e infundir em 30-60 min."),
        ("Amicacina", "Novamin", "Gram-negativos / Micobactérias", 1500, 750, 500, 250, "SF 0,9% ou SG 5% (100-200mL)", "Nefrotoxicidade, ototoxicidade irreversível", "Diluir em 100-200mL SF 0,9% ou SG 5% e infundir em 30-60 min."),
        ("Gentamicina", "Garamicina", "Sinergismo Endocardite / Gram-negativos", 500, 300, 160, 80, "SF 0,9% ou SG 5% (50-100mL)", "Nefrotoxicidade, ototoxicidade vestibular", "Diluir em 50-100mL SF 0,9% ou SG 5% e infundir em 30-60 min."),
        ("Ciprofloxacino", "Cipro", "ITU / Intra-abdominal / Pseudomonas", 1200, 800, 400, 400, "Bolsa Pronta (100-200mL)", "Intervalo QTc, tendinite, confusão em idosos", "Bolsa pronta para uso. Infundir em 60 min em veia calibrosa."),
        ("Levofloxacino", "Tavanic, Levaquin", "Pneumonia Comunitária / ITU", 750, 500, 250, 250, "Bolsa Pronta (100-150mL)", "Intervalo QTc, disglicemia, delírio em idosos", "Bolsa pronta para uso. Infundir lentamente em 60 a 90 min."),
        ("Metronidazol", "Flagyl", "Anaeróbios / Clostridioides difficile", 2000, 2000, 1500, 1000, "Bolsa Pronta (100mL)", "Neuropatia periférica, efeito dissulfiram", "Bolsa pronta de 500mg/100mL. Infundir em 30-60 min."),
        ("Clindamicina", "Dalacin C", "Anaeróbios / Pele", 2700, 2700, 2700, 2700, "SF 0,9% ou SG 5% (50-100mL)", "Colite pseudomembranosa", "Sem ajuste renal. PROIBIDO bolus EV direto. Diluir em 50-100mL SF 0,9% ou SG 5% e infundir em 20-60 min."),
        ("Tigeciclina", "Tygacil", "MDR Intra-abdominal / Pele", 200, 200, 200, 200, "SF 0,9% ou SG 5% (100mL)", "Hepatopatia grave (reduzir manutenção p/ 25mg 12/12h)", "Sem ajuste renal. Ajustar em Child-Pugh C. Diluir em 100mL SF 0,9% ou SG 5% e correr em 30-60 min."),
        ("Sulfametoxazol + Trimetoprima", "Bactrim", "Pneumocistose / Stenotrophomonas", 3200, 1600, 800, 400, "Exclusivo SG 5% (125mL por ampola)", "Hipercalemia, insuficiência renal", "Cada ampola (5mL) exige 125mL de SG 5%. Infundir em 60-90 min."),
        ("Azitromicina", "Zitromax", "Pneumonia Atípica", 500, 500, 500, 500, "SF 0,9% ou SG 5% (250-500mL)", "Prolongamento QTc, função hepática", "Sem ajuste renal. Diluir 500mg em 250mL e correr em 60 min."),
        ("Claritromicina", "Klaricid", "Pneumonia / Micobactérias", 1000, 500, 500, 250, "SF 0,9% ou SG 5% (250mL)", "Prolongamento QTc, interações CYP3A4, flebite", "Reconstituir APENAS com 10mL de Água Destilada (nunca SF). Diluir em 250mL SF 0,9% ou SG 5% e infundir em 60 min."),
        ("Fluconazol", "Zoltec", "Candidíase / Criptococose", 800, 400, 200, 200, "Bolsa Pronta (100mL)", "Função hepática, intervalo QTc, ajuste renal", "Bolsa pronta (200mg/100mL). Infundir em 60 min."),
        ("Anfotericina B Desoxicolato", "Fungizon", "Micoses Sistêmicas Graves", 100, 100, 100, 100, "Exclusivo SG 5% (500mL)", "Nefrotoxicidade grave, hipocalemia, hipomagnesemia", "PROIBIDO diluir em SF 0,9% (precipita). Diluir exclusivamente em SG 5%. Infundir em 4 a 6 horas."),
        ("Anfotericina B Lipossomal", "Ambisome", "Fúngicas Invasivas / Leishmaniose", 400, 400, 400, 400, "Exclusivo SG 5% (250-500mL)", "Eletrólitos (K+, Mg2+), creatinina", "INCOMPATÍVEL com SF 0,9%. Reconstituir em AD e diluir exclusivamente em SG 5%. Infundir em 2h."),
        ("Aciclovir", "Zovirax", "Herpes Simples / Encefalite / Zoster", 3000, 2000, 1000, 500, "SF 0,9% ou SG 5% (100mL)", "Nefrotoxicidade por cristalúria (manter hidratação)", "Diluir em 100mL SF 0,9% ou SG 5%. Infusão obrigatória em no mínimo 60 min.")
    ]
    cursor.executemany("""
        INSERT OR IGNORE INTO antimicrobianos 
        (nome_generico, nomes_comerciais, indicacao, dose_max_padrao_mg, dose_max_clcr30_50_mg, dose_max_clcr10_30_mg, dose_max_clcr10_mg, diluente_padrao, monitorizacao, farmacotecnia) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, atbs)

    cursor.execute("DROP TABLE IF EXISTS interacoes")
    cursor.execute("CREATE TABLE interacoes (id INTEGER PRIMARY KEY AUTOINCREMENT, droga_a TEXT, droga_b TEXT, gravidade TEXT, mecanismo TEXT, conduta TEXT)")
    interacoes = [
        ("Vancomicina", "Piperacilina + Tazobactam", "Grave", "Potencialização de nefrotoxicidade aguda sinérgica", "Monitorar creatinina e débito urinário diariamente; considerar Cefepima ou Meropenem."),
        ("Vancomicina", "Amicacina", "Grave", "Nefrotoxicidade e ototoxicidade aditivas/sinérgicas", "Monitorar creatinina diária e vancocinemia."),
        ("Vancomicina", "Furosemida", "Moderada", "Aumento do risco de nefrotoxicidade e ototoxicidade", "Monitorar função renal e balanço hídrico."),
        ("Ceftriaxona", "Ringer Lactato", "Contraindicada", "Precipitação intravascular de ceftriaxona-cálcio", "Suspender diluição ou infusão simultânea com soluções contendo cálcio."),
        ("Meropenem", "Ácido Valproico", "Grave", "Redução drástica (60-100%) dos níveis séricos de valproato em 24h", "Substituir anticonvulsivante (ex: Levetiracetam ou Fenitoína)."),
        ("Ciprofloxacino", "Amiodarona", "Maior", "Prolongamento sinérgico do intervalo QTc", "Monitorização eletrocardiográfica e de K+/Mg2+."),
        ("Levofloxacino", "Amiodarona", "Maior", "Prolongamento sinérgico do intervalo QTc", "Monitorar ECG e eletrólitos."),
        ("Fluconazol", "Amiodarona", "Maior", "Inibição do metabolismo da amiodarona + prolongamento QTc", "Monitorar ECG."),
        ("Linezolida", "Fentanil", "Maior", "Risco de Síndrome Serotoninérgica", "Vigiar hipertermia, clônus e agitação."),
        ("Linezolida", "Escitalopram", "Contraindicada", "Alto risco de Síndrome Serotoninérgica", "Suspender ISRS ou substituir Linezolida."),
        ("Omeprazol", "Clopidogrel", "Moderada", "Inibição competitiva da CYP2C19 reduzindo eficácia do clopidogrel", "Substituir Omeprazol por Pantoprazol se indicado.")
    ]
    cursor.executemany("INSERT INTO interacoes (droga_a, droga_b, gravidade, mecanismo, conduta) VALUES (?, ?, ?, ?, ?)", interacoes)

    cursor.execute("DROP TABLE IF EXISTS regras_farmacotecnicas")
    cursor.execute("CREATE TABLE regras_farmacotecnicas (id INTEGER PRIMARY KEY AUTOINCREMENT, farmaco TEXT, condicao TEXT, alerta TEXT)")
    regras_farmaco = [
        ("dipirona", "ad", "Diluir Dipirona em Água Destilada (AD) aumenta risco de dor e flebite. Prefira SF 0,9% ou SG 5%."),
        ("dipirona", "agua destilada", "Diluir Dipirona em Água Destilada (AD) aumenta risco de dor e flebite. Prefira SF 0,9% ou SG 5%."),
        ("fenitoina", "sg", "INCOMPATÍVEL com Soro Glicosado (SG 5%) por precipitação. Utilizar exclusivamente SF 0,9%."),
        ("ampicilina", "sg", "Incompatível/baixa estabilidade em Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("clavulin", "sg", "Amoxicilina+Clavulanato EV é incompatível com SG 5%. Diluir exclusivamente em SF 0,9%."),
        ("amoxicilina", "sg", "Amoxicilina+Clavulanato EV é incompatível com SG 5%. Diluir exclusivamente em SF 0,9%."),
        ("ertapenem", "sg", "PROIBIDO diluir Ertapenem em Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("daptomicina", "sg", "INCOMPATÍVEL com Soro Glicosado (SG 5%). Diluir exclusivamente em SF 0,9%."),
        ("polimixina", "sf", "Polimixina B tem baixa estabilidade em SF 0,9%. Diluir exclusivamente em 300-500mL de SG 5%."),
        ("bactrim", "sf", "Sulfametoxazol+Trimetoprima EV deve ser diluído preferencialmente em SG 5% (125mL/ampola)."),
        ("sulfametoxazol", "sf", "Sulfametoxazol+Trimetoprima EV deve ser diluído preferencialmente em SG 5% (125mL/ampola)."),
        ("anfotericina", "sf", "PROIBIDO diluir Anfotericina B em SF 0,9% (precipitação imediata). Diluir exclusivamente em SG 5%."),
        ("ceftriaxona", "ringer", "CONTRAINDICADO: Ceftriaxona precipita com o cálcio do Ringer Lactato. Diluir em SF 0,9% ou SG 5%."),
        ("omeprazol", "sonda", "Omeprazol cápsula com microgrânulos gastro-resistentes não deve ser triturado em sonda enteral.")
    ]
    cursor.executemany("INSERT INTO regras_farmacotecnicas (farmaco, condicao, alerta) VALUES (?, ?, ?)", regras_farmaco)

    cursor.execute("DROP TABLE IF EXISTS comorbidades_risco")
    cursor.execute("CREATE TABLE comorbidades_risco (id INTEGER PRIMARY KEY AUTOINCREMENT, comorbidade TEXT, farmaco_contraindicado TEXT, alerta TEXT)")
    comorbidades = [
        ("Hepatopatia", "Tigeciclina", "Em hepatopatas graves (Child-Pugh C), reduzir manutenção para 25mg 12/12h."),
        ("Hepatopatia", "Ceftriaxona", "Risco de pseudolitíase biliar; se disfunção renal associada, não exceder 2g/dia."),
        ("DRC", "Nitrofurantoína", "Contraindicado em ClCr < 30 mL/min."),
        ("DRC", "Amicacina", "Alto risco nefrotóxico em DRC; considerar alternativa."),
        ("Demência", "Ciprofloxacino", "Quinolonas agravam delirium/confusão aguda em idosos com demência."),
        ("Demência", "Levofloxacino", "Quinolonas aumentam risco de delirium em idosos com demência."),
        ("Parkinson", "Metoclopramida", "CONTRAINDICADO na Doença de Parkinson. Substituir por Ondansetrona."),
        ("Parkinson", "Bromoprida", "CONTRAINDICADO na Doença de Parkinson. Substituir por Ondansetrona."),
        ("Parkinson", "Haloperidol", "Evitar na Doença de Parkinson por agravamento motor severo.")
    ]
    cursor.executemany("INSERT INTO comorbidades_risco (comorbidade, farmaco_contraindicado, alerta) VALUES (?, ?, ?)", comorbidades)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    setup_database()
