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
    # If you need Sunday as well, add:
    # "DOM": "Domingo"
}

TURNOS = {
    "Manhã": (datetime.strptime("07:00", "%H:%M").time(), datetime.strptime("12:00", "%H:%M").time()),
    "Tarde": (datetime.strptime("12:01", "%H:%M").time(), datetime.strptime("18:00", "%H:%M").time()),
    "Noite": (datetime.strptime("18:01", "%H:%M").time(), datetime.strptime("23:00", "%H:%M").time())
}

MAX_COMBINACOES = 100000  # limite de segurança para geração

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
        (disciplina1, inicio1, disciplina2, inicio2, dia, fim1, fim2)
        Todos os horários formatados como "HH:MM" para exibição.
    """
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
                "dia": horario['dia'],
                "inicio": horario['inicio'],
                "fim": horario['fim']
            })

    for h1, h2 in combinations(todos_horarios, 2):
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
                h2['fim'].strftime("%H:%M")
            ))

    return (len(conflitos) > 0), conflitos


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
st.markdown("Etapa 1: selecione livremente as disciplinas que você se propõe a lecionar. Etapa 2: geramos sugestões sem conflito e com pontuação.")

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
        # Removido: 'filtro_nome_disc_busca'
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

        # Removido: campo de busca e normalização
        # Agora o multiselect usa diretamente todas as disciplinas disponíveis
        filtro_disciplinas = st.multiselect("Disciplinas", options=op_disciplinas, key='filtro_disciplinas')

        # Novos filtros: Códigos e Turmas
        filtro_codigos = st.multiselect("Códigos", options=op_codigos, key='filtro_codigos')
        filtro_turmas = st.multiselect("Turmas", options=op_turmas, key='filtro_turmas')

        # Demais filtros
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

    # Aplica filtros da Etapa 1 (sem alerta de conflito)
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

    # Estado atual como set; ROW_ID como string
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
            num_rows="fixed"  # trava estrutura de linhas
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

    disciplinas_selecionadas_ids = set(map(str, st.session_state.get("selecionados_ids", [])))
    selecionadas_full = df_base[df_base["ROW_ID"].astype(str).isin(disciplinas_selecionadas_ids)].copy()

    st.divider()

    # ETAPA 2: Refinar seleção e Gerar até 4 sugestões (sem relatório de conflitos no início)
    st.header("Etapa 2 • Refinar Seleção e Gerar Sugestões")

    col1, col2, col3 = st.columns(3)
    with col1:
        alvo_num_disciplinas = st.number_input(
            "Número de disciplinas (0 = usar todas as selecionadas)",
            min_value=0, max_value=12, value=0, step=1
        )
    with col2:
        alvo_qtd_dias = st.radio(
            "Dias totais na semana",
            options=["Qualquer", 2, 3, 4],
            index=0,
            horizontal=True
        )
    with col3:
        turnos_pref = st.multiselect("Turnos de preferência (usados no score)", options=list(TURNOS.keys()))

    gerar_sugestoes = st.button("Gerar sugestões (até 4)", type="primary")

    sugestoes = []
    todas_validas = []
    combinacoes_geradas = 0

    if gerar_sugestoes:
        if selecionadas_full.empty:
            st.warning("Selecione ao menos uma disciplina na Etapa 1 antes de gerar sugestões.")
        else:
            k = alvo_num_disciplinas if alvo_num_disciplinas > 0 else len(selecionadas_full)

            if k <= 0:
                st.warning("Número de disciplinas inválido.")
            elif k > len(selecionadas_full):
                st.warning(f"Você selecionou {len(selecionadas_full)} disciplina(s), mas pediu uma grade com {k}.")
            else:
                from math import comb
                try:
                    total_combos = comb(len(selecionadas_full), k)
                except ValueError:
                    total_combos = MAX_COMBINACOES + 1

                if total_combos > MAX_COMBINACOES:
                    st.warning(
                        f"Muitas combinações possíveis ({total_combos:,}). "
                        f"Geraremos um subconjunto para evitar lentidão."
                    )

                indices = list(selecionadas_full.index)
                for combo_indices in combinations(indices, k):
                    combinacoes_geradas += 1
                    if combinacoes_geradas > MAX_COMBINACOES:
                        break

                    df_combo = selecionadas_full.loc[list(combo_indices)].copy()

                    # 1) Conflitos
                    tem_conf, _ = check_conflito(df_combo)
                    if tem_conf:
                        continue

                    # 2) Dias totais (se exigido)
                    if alvo_qtd_dias in {2, 3, 4} and dias_totais_da_grade(df_combo) != alvo_qtd_dias:
                        continue

                    # 3) Regra institucional: apenas dois turnos consecutivos
                    tset = turnos_da_grade(df_combo)
                    if not is_turno_set_permitido(tset):
                        continue

                    todas_validas.append(df_combo)

                todas_validas_sorted = sorted(
                    todas_validas,
                    key=lambda dfc: score_combo(
                        dfc,
                        turnos_pref,
                        alvo_qtd_dias if alvo_qtd_dias != "Qualquer" else None
                    ),
                    reverse=True
                )

                sugestoes = todas_validas_sorted[:4]

                st.success(f"Geradas {len(sugestoes)} sugestão(ões). Combinações válidas encontradas: {len(todas_validas_sorted)}.")

    # Relatório de conflitos da seleção (apenas nesta etapa)
    if not selecionadas_full.empty:
        tem_conf, conflitos = check_conflito(selecionadas_full)
        if tem_conf and conflitos:
            with st.expander("Relatório de conflitos na seleção (Etapa 1)", expanded=False):
                for (d1, t1, d2, t2, dia, faixa1, faixa2) in conflitos:
                    st.write(f"- {dia}: {d1} ({t1}) {faixa1} ⟂ {d2} ({t2}) {faixa2}")
        else:
            st.caption("Sua Seleção (Etapa 1) não contém conflitos.")

    # Mostra até 4 sugestões (Etapa 2)
    if sugestoes:
        for i, sug in enumerate(sugestoes, start=1):
            st.subheader(f"Sugestão #{i} (Etapa 2)")
            view_cols = [c for c in ['CODIGO', 'DISCIPLINA', 'CURSO', 'TURMA', 'Dia 1', 'Dia 2'] if c in sug.columns]
            st.caption(f"Dias totais: {dias_totais_da_grade(sug)} • Score: {score_combo(sug, turnos_pref, alvo_qtd_dias if alvo_qtd_dias != 'Qualquer' else None)}")
            st.dataframe(sug[view_cols], use_container_width=True, hide_index=True)
            st.divider()

    # ETAPA 3: Listar todas as opções válidas
    st.header("Etapa 3 • Todas as Opções Válidas (ordenadas por score)")
    if gerar_sugestoes and todas_validas:
        todas_validas_sorted = sorted(
            todas_validas,
            key=lambda dfc: score_combo(dfc, turnos_pref, alvo_qtd_dias if alvo_qtd_dias != "Qualquer" else None),
            reverse=True
        )

        for i, opt in enumerate(todas_validas_sorted, start=1):
            with st.expander(f"Opção #{i} • Dias: {dias_totais_da_grade(opt)} • Score: {score_combo(opt, turnos_pref, alvo_qtd_dias if alvo_qtd_dias != 'Qualquer' else None)}"):
                view_cols = [c for c in ['CODIGO', 'DISCIPLINA', 'CURSO', 'TURMA', 'Dia 1', 'Dia 2'] if c in opt.columns]
                st.dataframe(opt[view_cols], use_container_width=True, hide_index=True)
    elif gerar_sugestoes and not todas_validas:
        st.info("Nenhuma combinação válida foi encontrada com os critérios da Etapa 2.")
