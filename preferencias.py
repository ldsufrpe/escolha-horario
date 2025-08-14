# python
import streamlit as st
import pandas as pd
from datetime import datetime
from itertools import combinations
import unicodedata
import io

# --- CONFIGURAÇÕES E CONSTANTES ---

DIAS_SEMANA_MAP = {
    "SEG": "Segunda-feira",
    "TER": "Terça-feira",
    "QUA": "Quarta-feira",
    "QUI": "Quinta-feira",
    "SEX": "Sexta-feira",
    "SAB": "Sábado"
}

TURNOS = {
    "Manhã": (datetime.strptime("07:00", "%H:%M").time(), datetime.strptime("12:00", "%H:%M").time()),
    "Tarde": (datetime.strptime("12:01", "%H:%M").time(), datetime.strptime("18:00", "%H:%M").time()),
    "Noite": (datetime.strptime("18:01", "%H:%M").time(), datetime.strptime("23:00", "%H:%M").time())
}

MAX_COMBINACOES = 100000  # limite de segurança para geração

# --- ESTADO GLOBAL DO FLUXO E FIXAÇÃO ---

if "current_step" not in st.session_state:
    # 1: Seleção; 2: Revisão+Fixar; 3: Agrupar+Gerar
    st.session_state["current_step"] = 1

# Mantém compatibilidade com seleção atual
if "selecionados_ids" not in st.session_state:
    st.session_state["selecionados_ids"] = []

# Conjunto de ROW_IDs fixos (subconjunto de selecionados)
if "fixos_ids" not in st.session_state:
    st.session_state["fixos_ids"] = set()

# Sinaliza que a seleção foi confirmada na Etapa 2
if "confirmado" not in st.session_state:
    st.session_state["confirmado"] = False

# Grupos de fixas (Etapa 3): mapa ROW_ID -> rótulo do grupo (ex.: "Grupo A"/"Grupo B"/"Grupo C"/"Sem grupo")
if "mapa_grupos_fixas" not in st.session_state:
    st.session_state["mapa_grupos_fixas"] = {}  # {ROW_ID: label}

# Configuração de como tratar fixas "Sem grupo"
if "singles_sao_obrigatorias" not in st.session_state:
    st.session_state["singles_sao_obrigatorias"] = False

def _ensure_fixed_subset_of_selected():
    """Garante que fixos ⊆ selecionados."""
    st.session_state["fixos_ids"] = set(map(str, st.session_state.get("fixos_ids", set()))) & set(map(str, st.session_state.get("selecionados_ids", [])))

def _go_to_step(step: int):
    st.session_state["current_step"] = int(step)

def _style_bold_fixed(df_show: pd.DataFrame, fixed_ids: set):
    """Retorna um Styler com linhas fixas em negrito."""
    if "ROW_ID" not in df_show.columns:
        return df_show
    df_show = df_show.copy()
    df_show["ROW_ID"] = df_show["ROW_ID"].astype(str)
    df_show = df_show.set_index("ROW_ID", drop=False)
    def _bold_row(idx):
        return ['font-weight: bold'] * len(df_show.columns) if idx in fixed_ids else [''] * len(df_show.columns)
    try:
        return df_show.style.apply(lambda s: _bold_row(s.name), axis=1)
    except Exception:
        return df_show

# --- FUNÇÕES AUXILIARES ---

def _normalize(s: str) -> str:
    """Remove acentos e converte para minúsculas para comparações insensíveis."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower().strip()

@st.cache_data
def parse_horarios(horario_str):
    """Converte a string de horário do CSV em uma lista de dicionários estruturados."""
    horarios_processados = []
    if not isinstance(horario_str, str):
        return []

    horario_str = horario_str.replace(" as ", " às ").replace(" as ", " às ")
    partes = horario_str.split(',')

    for parte in partes:
        if 'às' not in parte:
            continue
        try:
            dia_str, tempo_str = parte.split('-', 1)
            dia_str = dia_str.strip().upper()

            if dia_str not in DIAS_SEMANA_MAP:
                continue

            inicio_str, fim_str = [t.strip() for t in tempo_str.split('às')]

            horario = {
                "dia": DIAS_SEMANA_MAP[dia_str],
                "inicio": datetime.strptime(inicio_str, "%H:%M").time(),
                "fim": datetime.strptime(fim_str, "%H:%M").time()
            }
            horarios_processados.append(horario)
        except (ValueError, IndexError):
            continue

    return horarios_processados


def get_turno(horario):
    """Determina o turno de um determinado horário."""
    for nome_turno, (inicio_turno, fim_turno) in TURNOS.items():
        if inicio_turno <= horario['inicio'] <= fim_turno:
            return nome_turno
    return "Indefinido"


def _build_horario_completo(df: pd.DataFrame) -> pd.DataFrame:
    """Garante colunas 'Dia 1', 'Dia 2' e 'horario_completo' a partir de possíveis variações do CSV."""
    if df is None or df.empty:
        return df

    # Renomeia 'HORÁRIO' -> 'Dia 1' (se existir)
    if 'HORÁRIO' in df.columns and 'Dia 1' not in df.columns:
        df = df.rename(columns={'HORÁRIO': 'Dia 1'})

    # Tenta identificar uma coluna "Dia 2"
    col_dia2_original = None

    if '' in df.columns:
        col_dia2_original = ''
    else:
        unnamed_cols = [col for col in df.columns if str(col).startswith('Unnamed')]
        if unnamed_cols:
            col_dia2_original = unnamed_cols[0]

    # Garante as colunas 'Dia 1' e 'Dia 2'
    if 'Dia 1' not in df.columns:
        df['Dia 1'] = ''

    if col_dia2_original:
        df = df.rename(columns={col_dia2_original: 'Dia 2'})
    if 'Dia 2' not in df.columns:
        df['Dia 2'] = ''

    # Monta 'horario_completo'
    df['horario_completo'] = (df['Dia 1'].fillna('') + ', ' + df['Dia 2'].fillna('')).str.strip(', ').fillna('')

    return df


@st.cache_data
def carregar_disciplinas(uploaded_file):
    """Carrega e processa as disciplinas do arquivo CSV."""
    if uploaded_file is None:
        return pd.DataFrame()

    try:
        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
        df = pd.read_csv(stringio)

        # Garante colunas de horário e a coluna composta
        df = _build_horario_completo(df)

        if 'Dia 1' not in df.columns and df.get('horario_completo', '').eq('').all():
            st.error("O arquivo CSV precisa ter uma coluna de horário identificável (ex.: 'HORÁRIO').")
            return pd.DataFrame()

        # Normaliza nomes de colunas principais
        df.rename(columns={
            'CÓDIGO': 'CODIGO',
            'COMPONENTE CURRICULAR': 'DISCIPLINA',
        }, inplace=True)

        # Constrói objetos de horário
        df['horarios_obj'] = df['horario_completo'].apply(parse_horarios)

        # Mantém apenas linhas com algum horário válido
        df = df[df['horarios_obj'].map(len) > 0].copy()

        # Adiciona colunas derivadas
        df['TURNOS'] = df['horarios_obj'].apply(lambda horarios: list(set(get_turno(h) for h in horarios)))
        df['DIAS'] = df['horarios_obj'].apply(lambda horarios: list(set(h['dia'] for h in horarios)))

        # Identificador estável da linha para persistir seleção
        def _mk_id(row):
            return f"{row.get('CODIGO','')}-{row.get('TURMA','')}-{row.get('Dia 1','')}-{row.get('Dia 2','')}"
        df['ROW_ID'] = df.apply(_mk_id, axis=1).astype(str)

        return df

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o arquivo CSV: {e}")
        return pd.DataFrame()


def ensure_computed_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garante que as colunas derivadas existam antes de filtrar."""
    if df is None or df.empty:
        return df

    if 'horarios_obj' not in df.columns:
        if 'horario_completo' not in df.columns:
            df = _build_horario_completo(df)
        df['horarios_obj'] = df['horario_completo'].apply(parse_horarios)

    if 'DIAS' not in df.columns:
        df['DIAS'] = df['horarios_obj'].apply(lambda horarios: list(set(h['dia'] for h in horarios)))
    if 'TURNOS' not in df.columns:
        df['TURNOS'] = df['horarios_obj'].apply(lambda horarios: list(set(get_turno(h) for h in horarios)))
    if 'ROW_ID' not in df.columns:
        def _mk_id(row):
            return f"{row.get('CODIGO','')}-{row.get('TURMA','')}-{row.get('Dia 1','')}-{row.get('Dia 2','')}"
        df['ROW_ID'] = df.apply(_mk_id, axis=1)
    df['ROW_ID'] = df['ROW_ID'].astype(str)

    return df


def check_conflito(disciplinas_selecionadas):
    """Verifica conflitos entre as disciplinas selecionadas.

    Retorna:
        (tem_conflito: bool, conflitos: list[tuple])
        Onde cada tupla é:
        (disciplina1, inicio1, disciplina2, inicio2, dia, fim1, fim2, turma1, turma2)
    """
    from itertools import combinations as _comb
    conflitos = []
    try:
        if getattr(disciplinas_selecionadas, "empty", False) or len(disciplinas_selecionadas) < 2:
            return False, []
    except TypeError:
        pass

    todos_horarios = []
    for _, disc in disciplinas_selecionadas.iterrows():
        horarios = disc.get('horarios_obj') or []
        for horario in horarios:
            if not horario or 'inicio' not in horario or 'fim' not in horario or 'dia' not in horario:
                continue
            todos_horarios.append({
                "disciplina": disc.get('DISCIPLINA', 'N/A'),
                "turma": disc.get('TURMA', 'N/A'),
                "dia": horario['dia'],
                "inicio": horario['inicio'],
                "fim": horario['fim']
            })

    for h1, h2 in _comb(todos_horarios, 2):
        if h1['dia'] != h2['dia']:
            continue
        if h1['inicio'] < h2['fim'] and h2['inicio'] < h1['fim']:
            conflitos.append((
                h1['disciplina'],
                h1['inicio'].strftime("%H:%M"),
                h2['disciplina'],
                h2['inicio'].strftime("%H:%M"),
                h1['dia'],
                h1['fim'].strftime("%H:%M"),
                h2['fim'].strftime("%H:%M"),
                h1.get('turma', 'N/A'),
                h2.get('turma', 'N/A'),
            ))

    return (len(conflitos) > 0), conflitos

def conflitos_com_turma_legenda(conflitos):
    """Formata conflitos incluindo TURMA para exibição."""
    linhas = []
    for (d1, t1, d2, t2, dia, f1, f2, turma1, turma2) in conflitos:
        linhas.append(f"- {dia}: {d1} (Turma {turma1}) {t1}-{f1} ⟂ {d2} (Turma {turma2}) {t2}-{f2}")
    return linhas


def dias_totais_da_grade(df_grade: pd.DataFrame) -> int:
    """Conta o número de dias distintos na combinação."""
    dias = set()
    for _, r in df_grade.iterrows():
        for d in r.get("DIAS", []):
            dias.add(d)
    return len(dias)


def score_combo(df_grade: pd.DataFrame, turnos_pref: list, alvo_qtd_dias) -> int:
    """Calcula score de uma combinação para ordenação."""
    score = 0
    if turnos_pref:
        for _, r in df_grade.iterrows():
            turnos_disc = r.get("TURNOS", [])
            if any(t in turnos_pref for t in turnos_disc):
                score += 1
    if alvo_qtd_dias in {2, 3, 4}:
        if dias_totais_da_grade(df_grade) == alvo_qtd_dias:
            score += 2
    if {'CURSO', 'DISCIPLINA', 'TURMA'}.issubset(df_grade.columns):
        grp = df_grade.groupby(['CURSO', 'DISCIPLINA'])['TURMA'].nunique()
        extras = (grp[grp > 1] - 1).sum()
        if pd.notna(extras):
            score += int(extras)
    return score


def turnos_da_grade(df_grade: pd.DataFrame) -> set:
    """Retorna o conjunto de turnos presentes na combinação."""
    turnos_set = set()
    for _, r in df_grade.iterrows():
        for t in r.get("TURNOS", []):
            if t:
                turnos_set.add(t)
    return turnos_set


def is_turno_set_permitido(turnos_set: set) -> bool:
    """Aceita somente dois turnos consecutivos: {Manhã, Tarde} ou {Tarde, Noite}."""
    return turnos_set in ({"Manhã", "Tarde"}, {"Tarde", "Noite"})


# --- INTERFACE DA APLICAÇÃO WEB ---

st.set_page_config(page_title="Montador de Grade Horária", layout="wide")

st.title("🛠️ Montador de Grade Horária")
st.markdown("Fluxo: Etapa 1 (seleção) → Etapa 2 (revisão e fixação) → Etapa 3 (agrupar fixas e gerar).")

# --- BARRA LATERAL COM FILTROS DA ETAPA 1 ---
with st.sidebar:
    st.header("Etapa 1 • Carregar e Filtrar Ofertas")
    uploaded_file = st.file_uploader(
        "Faça o upload do arquivo de disciplinas (.csv)",
        type="csv"
    )
    st.divider()

    df_disciplinas = carregar_disciplinas(uploaded_file)

    # Botão de limpeza geral dos filtros da Etapa 1
    limpar = st.button("Limpar filtros (Etapa 1)", use_container_width=True)

    if limpar:
        st.session_state['filtro_disciplinas'] = []
        st.session_state['filtro_codigos'] = []
        st.session_state['filtro_turmas'] = []
        st.session_state['filtro_cursos'] = []
        st.session_state['filtro_turnos'] = []
        st.session_state['filtro_dias'] = []
        st.rerun()

    if not df_disciplinas.empty:
        st.subheader("Filtros (Etapa 1)")
        # Preparação de opções
        op_disciplinas = sorted(df_disciplinas['DISCIPLINA'].dropna().unique()) if 'DISCIPLINA' in df_disciplinas.columns else []
        op_codigos = sorted(df_disciplinas['CODIGO'].dropna().unique()) if 'CODIGO' in df_disciplinas.columns else []
        op_turmas = sorted(df_disciplinas['TURMA'].dropna().unique()) if 'TURMA' in df_disciplinas.columns else []
        cursos_disponiveis = sorted(df_disciplinas['CURSO'].dropna().unique()) if 'CURSO' in df_disciplinas.columns else []
        turnos_disponiveis = sorted(list(TURNOS.keys()))
        dias_disponiveis = sorted(list(DIAS_SEMANA_MAP.values()))

        filtro_disciplinas = st.multiselect("Disciplinas", options=op_disciplinas, key='filtro_disciplinas')
        filtro_codigos = st.multiselect("Códigos", options=op_codigos, key='filtro_codigos')
        filtro_turmas = st.multiselect("Turmas", options=op_turmas, key='filtro_turmas')
        filtro_cursos = st.multiselect("Cursos", options=cursos_disponiveis, key='filtro_cursos')
        filtro_turnos = st.multiselect("Turnos", options=turnos_disponiveis, key='filtro_turnos')
        filtro_dias = st.multiselect("Dias da semana", options=dias_disponiveis, key='filtro_dias')
    else:
        filtro_disciplinas = []
        filtro_codigos = []
        filtro_turmas = []
        filtro_cursos = []
        filtro_turnos = []
        filtro_dias = []

# --- ÁREA PRINCIPAL ---
if uploaded_file is None:
    st.info("Aguardando o upload do arquivo de disciplinas na barra lateral.")
elif df_disciplinas.empty:
    st.error("Não foi possível carregar as disciplinas do arquivo. Verifique o formato.")
else:
    # Estado de seleção persistente (Etapa 1)
    if "selecionados_ids" not in st.session_state:
        st.session_state["selecionados_ids"] = []

    # Base completa com colunas derivadas e ROW_ID
    df_base = ensure_computed_columns(df_disciplinas.copy())

    if "ROW_ID" not in df_base.columns:
        df_base = df_base.reset_index(drop=False).rename(columns={"index": "ROW_ID"})
    df_base["ROW_ID"] = df_base["ROW_ID"].astype(str)

    # Aplica filtros da Etapa 1
    df_filtrado = df_base.copy()
    if filtro_disciplinas and 'DISCIPLINA' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['DISCIPLINA'].isin(filtro_disciplinas)]
    if filtro_codigos and 'CODIGO' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['CODIGO'].isin(filtro_codigos)]
    if filtro_turmas and 'TURMA' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['TURMA'].isin(filtro_turmas)]
    if filtro_cursos and 'CURSO' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['CURSO'].isin(filtro_cursos)]
    if filtro_turnos and 'TURNOS' in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado['TURNOS'].apply(lambda turnos: any(t in filtro_turnos for t in turnos))]
    if filtro_dias and 'DIAS' in df_filtrado.columns:
        df_filtrado = df_filtrado[
            df_filtrado['DIAS'].apply(lambda dias_disciplina: set(filtro_dias).issubset(set(dias_disciplina)))
        ]

    # ETAPA 1: Tabela e seleção livre
    st.header("Etapa 1 • Ofertas Filtradas")
    st.markdown("Selecione livremente qualquer número de disciplinas. Conflitos não são validados nesta etapa.")

    selected_ids = set(map(str, st.session_state.get("selecionados_ids", [])))
    df_filtrado = df_filtrado.copy()
    df_filtrado["ROW_ID"] = df_filtrado["ROW_ID"].astype(str)

    # Garante existência do ROW_ID
    if "ROW_ID" not in df_filtrado.columns:
        if df_filtrado.index.isin(df_base.index).all():
            df_filtrado["ROW_ID"] = df_base.loc[df_filtrado.index, "ROW_ID"].astype(str)
        else:
            df_filtrado = df_filtrado.reset_index(drop=True)
            df_filtrado["ROW_ID"] = df_filtrado.index.astype(str)

    # Coluna de seleção baseada no estado
    df_filtrado["Selecionar"] = df_filtrado["ROW_ID"].isin(selected_ids)

    # Colunas a exibir
    colunas_para_exibir = ['Selecionar', 'DISCIPLINA', 'TURMA', 'Dia 1', 'Dia 2', 'ROW_ID']
    colunas_existentes = [col for col in colunas_para_exibir if col in df_filtrado.columns]

    # Ordem estável
    ordem_estavel = [c for c in ['DISCIPLINA', 'TURMA', 'Dia 1', 'Dia 2', 'ROW_ID'] if c in df_filtrado.columns]
    if ordem_estavel:
        df_filtrado.sort_values(by=ordem_estavel, inplace=True, kind="mergesort")

    # View para o editor
    df_view = df_filtrado[colunas_existentes].copy()
    df_view["ROW_ID"] = df_view["ROW_ID"].astype(str)
    df_view = df_view.set_index("ROW_ID", drop=False)

    # Ações de seleção em massa (operam sobre linhas visíveis)
    current_visible_ids = df_view["ROW_ID"].astype(str).tolist()
    a1, a2 = st.columns(2)
    with a1:
        if st.button("Selecionar todos (visíveis)", use_container_width=True):
            new_state = set(map(str, st.session_state.get("selecionados_ids", [])))
            new_state |= set(current_visible_ids)
            st.session_state["selecionados_ids"] = list(new_state)
            st.rerun()
    with a2:
        if st.button("Limpar seleção (visíveis)", use_container_width=True):
            new_state = set(map(str, st.session_state.get("selecionados_ids", [])))
            new_state -= set(current_visible_ids)
            st.session_state["selecionados_ids"] = list(new_state)
            st.rerun()

    column_config = {
        "Selecionar": st.column_config.CheckboxColumn(
            "Selecionar",
            help="Marque para selecionar esta disciplina",
            default=False
        )
    }
    for c in [c for c in df_view.columns if c != "Selecionar"]:
        column_config[c] = st.column_config.Column(c, disabled=True)

    # FORM: evita reruns durante os cliques e consolida no submit
    with st.form("form_editor_selecao", clear_on_submit=False):
        df_editado = st.data_editor(
            df_view,
            hide_index=True,
            use_container_width=True,
            key="editor_disciplinas",
            column_config=column_config,
            num_rows="fixed"
        )
        submitted = st.form_submit_button("Aplicar seleção")

    # Atualiza estado somente no submit (estável e previsível)
    if submitted and not df_editado.empty:
        if "ROW_ID" in df_editado.columns:
            current_visible_ids = df_editado["ROW_ID"].astype(str).tolist()
            selected_in_view_ids = set(df_editado.loc[df_editado["Selecionar"], "ROW_ID"].astype(str).tolist())
        else:
            current_visible_ids = list(df_editado.index.astype(str))
            selected_in_view_ids = set(df_editado.index[df_editado["Selecionar"]].astype(str).tolist())

        new_state = set(map(str, st.session_state.get("selecionados_ids", [])))
        new_state -= set(current_visible_ids)
        new_state |= selected_in_view_ids
        st.session_state["selecionados_ids"] = list(new_state)
        st.success("Seleção aplicada.")

    # Seleção corrente (DataFrame)
    disciplinas_selecionadas_ids = set(map(str, st.session_state.get("selecionados_ids", [])))
    selecionadas_full = df_base[df_base["ROW_ID"].astype(str).isin(disciplinas_selecionadas_ids)].copy()

    # Navegação do fluxo: Etapa 1 → Etapa 2
    st.divider()
    nav_col1, nav_col2 = st.columns([1, 1])
    with nav_col1:
        avancar_disabled = selecionadas_full.empty
        if st.button("Próxima etapa (revisar e fixar)", disabled=avancar_disabled, use_container_width=True):
            _ensure_fixed_subset_of_selected()
            st.session_state["confirmado"] = False
            _go_to_step(2)
    with nav_col2:
        if st.button("Reiniciar fluxo", use_container_width=True):
            st.session_state["selecionados_ids"] = []
            st.session_state["fixos_ids"] = set()
            st.session_state["confirmado"] = False
            st.session_state["mapa_grupos_fixas"] = {}
            st.session_state["singles_sao_obrigatorias"] = False
            _go_to_step(1)
            st.rerun()

    # ETAPA 2: Revisão e Fixação (com relatório de conflitos aqui)
    if st.session_state["current_step"] == 2:
        st.header("Etapa 2 • Revisar Seleção e Fixar Disciplinas")
        _ensure_fixed_subset_of_selected()

        if selecionadas_full.empty:
            st.warning("Sua seleção está vazia. Volte à Etapa 1.")
        else:
            st.caption("Marque 'Fixar' para obrigar a presença dessa disciplina nos cenários/grupos da Etapa 3.")
            for _, row in selecionadas_full.iterrows():
                rid = str(row["ROW_ID"])
                label = f"Fixar | {row.get('CODIGO','')} — {row.get('DISCIPLINA','')} — Turma {row.get('TURMA','')}"
                atual = rid in st.session_state["fixos_ids"]
                novo_valor = st.checkbox(label, value=atual, key=f"fix_{rid}")
                if novo_valor:
                    st.session_state["fixos_ids"].add(rid)
                else:
                    st.session_state["fixos_ids"].discard(rid)

            # Relatório de conflitos movido para a Etapa 2 e incluindo TURMA
            if not selecionadas_full.empty:
                tem_conf, conflitos = check_conflito(selecionadas_full)
                if tem_conf and conflitos:
                    with st.expander("Relatório de conflitos na sua seleção (inclui Turma)", expanded=False):
                        for linha in conflitos_com_turma_legenda(conflitos):
                            st.write(linha)
                else:
                    st.caption("Sua Seleção não contém conflitos.")

            # Ações Etapa 2
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("Voltar para Etapa 1", use_container_width=True):
                    _go_to_step(1)
            with c2:
                if st.button("Confirmar e ir para agrupamento (Etapa 3)", use_container_width=True, type="primary"):
                    _ensure_fixed_subset_of_selected()
                    st.session_state["confirmado"] = True
                    # Inicializa grupos padrão: todos "Sem grupo"
                    mapa = {}
                    for rid in st.session_state["fixos_ids"]:
                        mapa[rid] = "Sem grupo"
                    st.session_state["mapa_grupos_fixas"] = mapa
                    # Regra: se há exatamente 1 fixa sem grupo, sugere obrigatória
                    st.session_state["singles_sao_obrigatorias"] = (len([1 for v in mapa.values() if v == "Sem grupo"]) == 1)
                    _go_to_step(3)

    # ETAPA 3: Agrupar fixas e gerar (sem geração automática fora do botão)
    if st.session_state["current_step"] >= 3 and st.session_state["confirmado"]:
        st.header("Etapa 3 • Agrupar disciplinas fixas e gerar combinações")

        # Preferências gerais de score e alvo
        pref_col1, pref_col2, pref_col3 = st.columns(3)
        with pref_col1:
            alvo_num_disciplinas = st.number_input(
                "Número de disciplinas (0 = tamanhos variados)",
                min_value=0, max_value=12, value=0, step=1
            )
        with pref_col2:
            alvo_qtd_dias = st.radio(
                "Dias totais na semana",
                options=["Qualquer", 2, 3, 4],
                index=0,
                horizontal=True
            )
        with pref_col3:
            turnos_pref = st.multiselect("Turnos de preferência (usados no score)", options=list(TURNOS.keys()))

        # UI de agrupamento das fixas
        st.subheader("Agrupamento das disciplinas fixas")
        fixed_ids_set = set(map(str, st.session_state.get("fixos_ids", set())))
        _ensure_fixed_subset_of_selected()

        base_df = selecionadas_full.copy()
        base_df["ROW_ID"] = base_df["ROW_ID"].astype(str)

        if not fixed_ids_set:
            st.info("Você não fixou disciplinas na Etapa 2. Você pode gerar combinações livremente.")
            df_fixas = pd.DataFrame(columns=base_df.columns)
        else:
            df_fixas = base_df[base_df["ROW_ID"].isin(fixed_ids_set)].copy()

        grupos_rotulos = ["Sem grupo", "Grupo A", "Grupo B", "Grupo C"]
        st.caption("Atribua cada fixa a um grupo. Você pode usar dois grupos para rodadas separadas (OR) ou marcar 'juntos' para exigir todos (AND).")

        # Controles por fixa
        for _, row in df_fixas.iterrows():
            rid = str(row["ROW_ID"])
            label = f"{row.get('CODIGO','')} — {row.get('DISCIPLINA','')} — Turma {row.get('TURMA','')}"
            default_group = st.session_state["mapa_grupos_fixas"].get(rid, "Sem grupo")
            st.session_state["mapa_grupos_fixas"][rid] = st.selectbox(
                f"Grupo de: {label}",
                options=grupos_rotulos,
                index=grupos_rotulos.index(default_group) if default_group in grupos_rotulos else 0,
                key=f"grp_{rid}"
            )

        # Opções de como combinar grupos
        st.markdown("Configuração de combinação dos grupos:")
        cfg1, cfg2 = st.columns([1, 1])
        with cfg1:
            combinar_grupos_juntos = st.toggle("Incluir grupos A/B/C juntos (AND)", value=False,
                                               help="Se ligado, as combinações exigem todos os grupos não vazios simultaneamente. Se desligado, geramos rodadas separadas para cada grupo não vazio (OR).")
        with cfg2:
            st.session_state["singles_sao_obrigatorias"] = st.toggle(
                "Fixas 'Sem grupo' são obrigatórias em todas as sugestões",
                value=st.session_state["singles_sao_obrigatorias"],
                help="Se houver exatamente 1 fixa sem grupo, manteremos este valor ligado por padrão."
            )

        # Botão para gerar
        gerar = st.button("Gerar combinações", type="primary", use_container_width=True)

        if gerar:
            # Calcula conjuntos obrigatórios conforme configuração
            grupos = {"Grupo A": set(), "Grupo B": set(), "Grupo C": set()}
            singles = set()
            if fixed_ids_set:
                for rid, rot in st.session_state["mapa_grupos_fixas"].items():
                    if rot in grupos:
                        grupos[rot].add(rid)
                    else:
                        singles.add(rid)

            # Define cenários (lista de conjuntos obrigatórios)
            cenarios = []
            grupos_nao_vazios = [g for g, s in grupos.items() if len(s) > 0]

            if fixed_ids_set:
                if combinar_grupos_juntos:
                    obrig = set().union(*[grupos[g] for g in grupos_nao_vazios]) if grupos_nao_vazios else set()
                    if st.session_state["singles_sao_obrigatorias"]:
                        obrig |= singles
                    cenarios = [obrig]
                else:
                    if grupos_nao_vazios:
                        for g in grupos_nao_vazios:
                            obrig = set(grupos[g])
                            if st.session_state["singles_sao_obrigatorias"]:
                                obrig |= singles
                            cenarios.append(obrig)
                    else:
                        obrig = singles if st.session_state["singles_sao_obrigatorias"] else set()
                        cenarios = [obrig]
            else:
                cenarios = [set()]

            # Funções auxiliares para validação
            def _combo_ok(df_combo: pd.DataFrame) -> bool:
                # 1) Conflitos
                tem_conf, _ = check_conflito(df_combo)
                if tem_conf:
                    return False
                # 2) Dias totais (se exigido)
                if alvo_qtd_dias in {2, 3, 4} and dias_totais_da_grade(df_combo) != alvo_qtd_dias:
                    return False
                # 3) Regra de turnos consecutivos
                tset = turnos_da_grade(df_combo)
                if not is_turno_set_permitido(tset):
                    return False
                return True

            # Mapeia ROW_ID -> índice de base_df
            id_to_idx = {rid: idx for idx, rid in zip(base_df.index, base_df["ROW_ID"])}

            total_validas_global = 0
            from itertools import combinations as _comb

            for idx_cen, obrig_rids in enumerate(cenarios, start=1):
                st.subheader(f"Cenário {idx_cen}")
                if obrig_rids:
                    st.caption("Obrigatórias neste cenário: " + ", ".join(
                        base_df[base_df["ROW_ID"].isin(obrig_rids)].apply(lambda r: f"{r['DISCIPLINA']} (Turma {r['TURMA']})", axis=1).tolist()
                    ))
                else:
                    st.caption("Sem disciplinas obrigatórias neste cenário.")

                obrig_idx = {id_to_idx[r] for r in obrig_rids if r in id_to_idx}
                indices = list(base_df.index)
                resto = [i for i in indices if i not in obrig_idx]

                # Se o usuário escolheu um alvo > 0, respeitar exatamente o tamanho
                if alvo_num_disciplinas > 0 and len(obrig_idx) > alvo_num_disciplinas:
                    st.warning(f"Alvo de {alvo_num_disciplinas} é menor que as obrigatórias deste cenário ({len(obrig_idx)}). Nenhuma combinação gerada para este cenário.")
                    continue

                todas_validas = []
                combinacoes_geradas = 0

                # Tamanhos a considerar
                if alvo_num_disciplinas == 0:
                    tamanhos = range(max(1, len(obrig_idx)), len(indices) + 1)
                else:
                    tamanhos = [alvo_num_disciplinas]

                for k in tamanhos:
                    if k < len(obrig_idx):
                        continue
                    if len(obrig_idx) == k:
                        # Combo é exatamente as obrigatórias
                        combo_idx = list(sorted(obrig_idx))
                        df_combo = base_df.loc[combo_idx].copy()
                        if _combo_ok(df_combo):
                            todas_validas.append(df_combo)
                        combinacoes_geradas += 1
                        if combinacoes_geradas >= MAX_COMBINACOES:
                            break
                    else:
                        for extra in _comb(resto, k - len(obrig_idx)):
                            combo_idx = list(sorted(obrig_idx)) + list(extra)
                            df_combo = base_df.loc[combo_idx].copy()
                            if _combo_ok(df_combo):
                                todas_validas.append(df_combo)
                            combinacoes_geradas += 1
                            if combinacoes_geradas >= MAX_COMBINACOES:
                                break
                    if combinacoes_geradas >= MAX_COMBINACOES:
                        break

                # Ordena e exibe
                todas_validas_sorted = sorted(
                    todas_validas,
                    key=lambda dfc: score_combo(
                        dfc,
                        turnos_pref,
                        alvo_qtd_dias if alvo_qtd_dias != "Qualquer" else None
                    ),
                    reverse=True
                )

                total_validas_global += len(todas_validas_sorted)

                if not todas_validas_sorted:
                    st.info("Nenhuma combinação válida encontrada neste cenário.")
                else:
                    st.success(f"Combinações válidas no cenário {idx_cen}: {len(todas_validas_sorted)} (limite: {MAX_COMBINACOES:,}).")

                    # Top 4 sugestões do cenário
                    sugestoes = todas_validas_sorted[:4]
                    if sugestoes:
                        for i, sug in enumerate(sugestoes, start=1):
                            st.subheader(f"Sugestão #{i} (Cenário {idx_cen})")
                            view_cols = [c for c in ['CODIGO', 'DISCIPLINA', 'CURSO', 'TURMA', 'Dia 1', 'Dia 2', 'ROW_ID'] if c in sug.columns]
                            st.caption(f"Dias totais: {dias_totais_da_grade(sug)} • Score: {score_combo(sug, turnos_pref, alvo_qtd_dias if alvo_qtd_dias != 'Qualquer' else None)}")
                            styled = _style_bold_fixed(sug[view_cols], fixed_ids_set)
                            try:
                                st.dataframe(styled, use_container_width=True, hide_index=True)
                            except Exception:
                                st.dataframe(sug[view_cols], use_container_width=True, hide_index=True)
                            st.divider()

                    # Lista completa do cenário
                    st.markdown("Todas as opções válidas deste cenário (ordenadas por score)")
                    for i, opt in enumerate(todas_validas_sorted, start=1):
                        with st.expander(f"Opção #{i} • Dias: {dias_totais_da_grade(opt)} • Score: {score_combo(opt, turnos_pref, alvo_qtd_dias if alvo_qtd_dias != 'Qualquer' else None)}"):
                            view_cols = [c for c in ['CODIGO', 'DISCIPLINA', 'CURSO', 'TURMA', 'Dia 1', 'Dia 2', 'ROW_ID'] if c in opt.columns]
                            styled = _style_bold_fixed(opt[view_cols], fixed_ids_set)
                            try:
                                st.dataframe(styled, use_container_width=True, hide_index=True)
                            except Exception:
                                st.dataframe(opt[view_cols], use_container_width=True, hide_index=True)

            if fixed_ids_set:
                st.caption(f"Destaque: linhas em negrito são disciplinas fixadas na Etapa 2.")

            # Rodapé de navegação
            foot1, foot2 = st.columns([1, 1])
            with foot1:
                if st.button("Voltar para Etapa 2"):
                    _go_to_step(2)
            with foot2:
                if st.button("Reiniciar fluxo (limpar seleção/fixos)"):
                    st.session_state["selecionados_ids"] = []
                    st.session_state["fixos_ids"] = set()
                    st.session_state["confirmado"] = False
                    st.session_state["mapa_grupos_fixas"] = {}
                    st.session_state["singles_sao_obrigatorias"] = False
                    _go_to_step(1)
                    st.rerun()