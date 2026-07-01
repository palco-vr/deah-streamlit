import os
import re
import time
from datetime import date, datetime
import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from wordcloud import WordCloud
import matplotlib.pyplot as plt

st.set_page_config(
    page_title="DEAH",
    page_icon="🌿",
    layout="centered",
    initial_sidebar_state="collapsed"
)

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)


st.markdown("""
<style>
.block-container {
    padding-top: 1.8rem;
    padding-bottom: 2rem;
    max-width: 760px;
}
div.stButton > button {
    width: 100%;
    min-height: 3.2rem;
    border-radius: 14px;
    font-size: 1.05rem;
    font-weight: 650;
    margin-top: 0.35rem;
    margin-bottom: 0.35rem;
}
.deah-card {
    background: #f8faf7;
    color: #1f2a24;
    border: 1px solid #dfe8dd;
    border-radius: 18px;
    padding: 1rem 1rem;
    margin: 0.8rem 0;
}

.deah-card h3,
.deah-card p {
    color: #1f2a24;
}
.small-muted {
    color: #666;
    font-size: 0.92rem;
}
h1, h2, h3 {
    line-height: 1.15;
}
[data-testid="stSidebar"] {
    display: none;
}

@media (max-width: 640px) {
    [data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        gap: 0.45rem !important;
    }

    [data-testid="stHorizontalBlock"] > div {
        flex: 1 1 0 !important;
        width: 50% !important;
        min-width: 0 !important;
    }

    div.stButton > button {
        min-height: 3.0rem;
        font-size: 0.88rem;
        padding-left: 0.25rem;
        padding-right: 0.25rem;
        white-space: normal;
    }
}

/* Barrinhas DEAH: cartões amplos e operáveis no celular */
.deah-scale-card {
    background: #f8faf7;
    color: #1f2a24;
    border: 1px solid #dfe8dd;
    border-radius: 18px;
    padding: 0.95rem 0.95rem 0.7rem 0.95rem;
    margin: 0.75rem 0 0.35rem 0;
}
.deah-scale-card .scale-title {
    font-weight: 700;
    font-size: 1.02rem;
    line-height: 1.25;
    margin-bottom: 0.25rem;
}
.deah-scale-card .scale-value {
    color: #4b5f54;
    font-size: 0.95rem;
    margin-top: -0.15rem;
    margin-bottom: 0.25rem;
}
.scale-anchors {
    display: flex;
    justify-content: space-between;
    color: #66756d;
    font-size: 0.82rem;
    margin-top: -0.35rem;
    margin-bottom: 1.15rem;
}

/* Aumenta a área útil do slider para o polegar */
div[data-testid="stSlider"] {
    padding-left: 0.45rem;
    padding-right: 0.45rem;
    padding-top: 0.25rem;
    padding-bottom: 0.45rem;
}
div[data-testid="stSlider"] label {
    display: none;
}

@media (max-width: 640px) {
    .deah-scale-card {
        padding: 1.05rem 0.85rem 0.8rem 0.85rem;
        margin: 0.95rem 0 0.4rem 0;
    }
    .deah-scale-card .scale-title {
        font-size: 1rem;
    }
    div[data-testid="stSlider"] {
        padding-left: 0.2rem;
        padding-right: 0.2rem;
        padding-top: 0.55rem;
        padding-bottom: 0.75rem;
    }
}

</style>
""", unsafe_allow_html=True)

METAPHOR_SCORE = {
    "Tempestade": 1,
    "Labirinto": 2,
    "Floresta escura": 3,
    "Mar agitado": 4,
    "Céu nublado": 5,
    "Montanha": 6,
    "Estrada aberta": 7,
    "Floresta iluminada": 8,
    "Céu ensolarado": 9,
    "Mar calmo": 10,
    "Outra": 5
}

NEGATIVE_ITEMS = {
    "tension": "Hoje me senti tenso(a)",
    "worry": "Hoje me senti preocupado(a)",
    "anxiety": "Hoje me senti ansioso(a)",
    "restlessness": "Hoje me senti inquieto(a)",
    "sadness": "Hoje me senti triste",
    "irritability": "Hoje me senti irritado(a)",
    "discouragement": "Hoje me senti desanimado(a)"
}

POSITIVE_ITEMS = {
    "relaxation": "Hoje me senti relaxado(a)",
    "confidence": "Hoje me senti confiante",
    "serenity": "Hoje me senti sereno(a)",
    "joy": "Hoje me senti alegre",
    "patience": "Hoje me senti paciente",
    "hope": "Hoje me senti esperançoso(a)"
}

STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os",
    "um", "uma", "com", "para", "por", "em", "no", "na", "nos", "nas",
    "que", "me", "eu", "hoje", "estou", "sinto", "sentindo", "muito",
    "mais", "menos", "foi", "era", "ser", "ter", "tem", "tive", "minha",
    "meu", "minhas", "meus", "isso", "essa", "esse", "também"
}

POSITIVE_WORDS = {
    "calmo", "tranquilo", "feliz", "leve", "seguro", "confiante",
    "esperançoso", "organizado", "animado", "sereno", "acolhido", "alegre"
}

NEGATIVE_WORDS = {
    "ansioso", "ansiedade", "medo", "triste", "cansado", "preocupado", "irritado",
    "tenso", "inquieto", "angustiado", "perdido", "pesado", "confuso"
}


def go_to(page):
    st.session_state.page = page
    st.rerun()


def init_state():
    if "page" not in st.session_state:
        st.session_state.page = "Início"
    if "diary_start_time" not in st.session_state:
        st.session_state.diary_start_time = time.time()


def get_participant(masked_id):
    result = (
        supabase.table("participants")
        .select("*")
        .eq("masked_id", masked_id.strip())
        .execute()
    )
    return result.data[0] if result.data else None




def calculate_current_day(participant):
    """Calcula automaticamente o dia do diário a partir da data de início."""
    started_at = participant.get("started_at") if participant else None
    if not started_at:
        return 1
    try:
        start_date = datetime.fromisoformat(str(started_at).replace("Z", "+00:00")).date()
    except Exception:
        try:
            start_date = date.fromisoformat(str(started_at)[:10])
        except Exception:
            return 1
    return max(1, min(7, (date.today() - start_date).days + 1))

def clean_words(text):
    words = re.findall(r"\b[a-záàâãéèêíïóôõöúçñ]+\b", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def normalize(value, min_value, max_value):
    if max_value == min_value:
        return 0
    return max(0, min(100, ((value - min_value) / (max_value - min_value)) * 100))


def count_words(text):
    if not text:
        return 0
    return len(clean_words(text))


def calculate_scores(df):
    df = df.copy()
    negative_cols = list(NEGATIVE_ITEMS.keys())
    positive_cols = list(POSITIVE_ITEMS.keys())

    for col in negative_cols + positive_cols:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["afeto_negativo"] = df[negative_cols].mean(axis=1)
    df["afeto_positivo"] = df[positive_cols].mean(axis=1)
    df["positivo_invertido"] = 4 - df["afeto_positivo"]
    df["desequilibrio_afetivo"] = df[["afeto_negativo", "positivo_invertido"]].mean(axis=1)
    df["balanco_afetivo"] = df["afeto_positivo"] - df["afeto_negativo"]
    df["metaphor_score"] = df["image_metaphor"].map(METAPHOR_SCORE).fillna(5)
    return df


def calculate_ipa(df):
    if len(df) < 2:
        return {"ipa_global": 0, "ipa_d": 0, "ipa_t": 0, "ipa_s": 0, "ipa_v": 0, "ipa_l": 0}

    df = df.sort_values("day_number").copy()
    metaphors = df["image_metaphor"].tolist()
    scores = df["metaphor_score"].tolist()

    n = len(df)
    max_transitions = n - 1
    diversity = len(set(metaphors))
    transitions = sum(1 for i in range(1, n) if metaphors[i] != metaphors[i - 1])

    ipa_d = normalize(diversity, 1, 7)
    ipa_t = normalize(transitions, 0, max_transitions)
    volatility = transitions / max_transitions if max_transitions > 0 else 0
    ipa_s = (1 - volatility) * 100
    direction = scores[-1] - scores[0]
    ipa_v = normalize(direction, -9, 9)

    all_text = " ".join(df["feeling_text"].dropna().astype(str)).lower()
    words = clean_words(all_text)

    if words:
        positive_count = sum(1 for w in words if w in POSITIVE_WORDS)
        negative_count = sum(1 for w in words if w in NEGATIVE_WORDS)
        ipa_l = normalize(positive_count - negative_count, -len(words), len(words))
    else:
        ipa_l = 50

    ipa_global = 0.20 * ipa_d + 0.20 * ipa_t + 0.20 * ipa_s + 0.20 * ipa_v + 0.20 * ipa_l

    return {
        "ipa_global": round(ipa_global, 2),
        "ipa_d": round(ipa_d, 2),
        "ipa_t": round(ipa_t, 2),
        "ipa_s": round(ipa_s, 2),
        "ipa_v": round(ipa_v, 2),
        "ipa_l": round(ipa_l, 2)
    }


def show_header_image():
    for img in [
        "assets/deah_abertura_desktop.png",
        "assets/deah_abertura.png",
        "assets/deah_abertura_mobile.png"
    ]:
        if os.path.exists(img):
            st.image(img, use_container_width=True)
            return


def top_nav():
    st.markdown(
        """
        <div style="text-align:center; padding-top:0.8rem; padding-bottom:0.4rem;">
            <div style="font-size:2.1rem; font-weight:800; line-height:1.35; margin-bottom:0.25rem;">
                🌿 DEAH
            </div>
            <div style="font-size:1rem; color:#4b5f54; line-height:1.35;">
                Diário Ecológico de Ansiedade, Estresse e Humor
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🏠 Início"):
            go_to("Início")
    with c2:
        if st.button("🌿 Participação"):
            go_to("Participação")

    c3, c4 = st.columns(2)
    with c3:
        if st.button("📝 Registro de Hoje"):
            go_to("Registro de Hoje")
    with c4:
        if st.button("📊 Resultados"):
            go_to("Resultados")

    if st.button("🔬 Pesquisador"):
        go_to("Pesquisador")

    st.divider()


def scale_help():
    st.markdown(
        '<div class="small-muted">Escala contínua: 0 = nada · 1 = pouco · 2 = moderadamente · 3 = bastante · 4 = extremamente</div>',
        unsafe_allow_html=True
    )


def deah_slider(label, key, value=0.0):
    """Slider afetivo em cartão, com valor visível e melhor usabilidade no celular."""
    st.markdown(
        f"""
        <div class="deah-scale-card">
            <div class="scale-title">{label}</div>
            <div class="scale-value">Ajuste a barrinha abaixo.</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    valor = st.slider(
        label,
        min_value=0.0,
        max_value=4.0,
        value=float(value),
        step=0.1,
        key=key,
        label_visibility="collapsed"
    )
    st.caption(f"Valor atual: {valor:.1f} · 0 nada · 4 extremamente")
    st.markdown(
        '<div class="scale-anchors"><span>0 · nada</span><span>4 · extremamente</span></div>',
        unsafe_allow_html=True
    )
    return valor


def deah_wellbeing_slider():
    """Slider de bem-estar em cartão, mantendo escala 0–100."""
    st.markdown(
        """
        <div class="deah-scale-card">
            <div class="scale-title">Bem-estar geral</div>
            <div class="scale-value">0 = muito baixo · 100 = muito alto</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    valor = st.slider(
        "Bem-estar geral",
        min_value=0.0,
        max_value=100.0,
        value=50.0,
        step=1.0,
        key="wellbeing_slider",
        label_visibility="collapsed"
    )
    st.caption(f"Valor atual: {valor:.0f}")
    st.markdown(
        '<div class="scale-anchors"><span>0 · muito baixo</span><span>100 · muito alto</span></div>',
        unsafe_allow_html=True
    )
    return valor


init_state()
top_nav()
page = st.session_state.page

if page == "Início":
    st.markdown("""
    ## Bem-vindo(a)

    O **DEAH** é um instrumento digital experimental para acompanhar,
    ao longo de alguns dias, experiências afetivas, paisagens emocionais
    e narrativas livres.

    O preenchimento leva cerca de **2 a 5 minutos por dia**.
    """)

    st.markdown("""
    <div class="deah-card">
    <h3>Participação voluntária</h3>
    <p>
    Você pode deixar de responder qualquer pergunta, interromper um registro
    em andamento ou encerrar sua participação a qualquer momento, sem necessidade
    de justificativa.
    </p>
    <p>
    Evite informar nomes completos, endereços ou dados que permitam identificar
    você ou outras pessoas.
    </p>
    <p>
    Este instrumento não realiza diagnóstico psicológico, psiquiátrico ou médico
    e não substitui acompanhamento profissional de saúde.
    </p>
    </div>
    """, unsafe_allow_html=True)

    col_ini1, col_ini2 = st.columns(2)

    with col_ini1:
        if st.button("🌿 Iniciar participação"):
            go_to("Participação")

    with col_ini2:
        if st.button("📝 Já participo"):
            go_to("Registro de Hoje")

elif page == "Participação":
    st.header("🌿 Iniciar participação")

    st.markdown("""
    Use uma **ID mascarada**. Ela não deve conter seu nome completo.

    Exemplos possíveis: `JPA001`, `MUSICO07`, `DEAH-TESTE`.
    """)

    masked_id = st.text_input("Digite sua ID mascarada")
    consent = st.checkbox("Li as informações e concordo voluntariamente em participar.")

    st.markdown("### Lembretes por 7 dias")
    reminder_consent = st.checkbox("Desejo receber um lembrete diário para preencher o DEAH durante 7 dias.")
    reminder_email = st.text_input("E-mail para lembrete, se desejar", placeholder="participante@email.com")

    if st.button("Confirmar participação"):
        if not masked_id.strip():
            st.error("Informe uma ID mascarada.")
        elif not consent:
            st.error("Marque o consentimento para continuar.")
        elif reminder_consent and not reminder_email.strip():
            st.error("Informe um e-mail para receber os lembretes ou desmarque a opção de lembrete.")
        elif get_participant(masked_id):
            st.warning("Essa ID já está cadastrada. Você já pode registrar o dia de hoje.")
        else:
            supabase.table("participants").insert({
                "masked_id": masked_id.strip(),
                "consent": consent,
                "started_at": date.today().isoformat(),
                "reminder_consent": reminder_consent,
                "reminder_email": reminder_email.strip() if reminder_consent else None,
                "reminder_channel": "email" if reminder_consent else None
            }).execute()
            st.success("Participação registrada com sucesso.")
            st.info("Agora toque em Registro de Hoje para preencher seu diário.")

    if st.button("📝 Ir para Registro de Hoje"):
        go_to("Registro de Hoje")


elif page == "Registro de Hoje":
    st.header("📝 Registro de Hoje")
    st.progress(0.15)

    st.markdown("### 1. Identificação")

    masked_id = st.text_input("ID mascarada")
    participant = get_participant(masked_id) if masked_id.strip() else None

    if masked_id.strip() and not participant:
        st.warning("Esta ID ainda não foi cadastrada.")
        if st.button("🌿 Cadastrar minha ID"):
            go_to("Participação")

    suggested_day = calculate_current_day(participant) if participant else 1
    day_number = st.number_input("Dia do diário", min_value=1, max_value=7, value=suggested_day)
    if participant:
        st.caption(f"Dia sugerido automaticamente pelo cadastro: {suggested_day}/7")

    st.divider()
    st.progress(0.30)
    st.markdown("### 2. Contexto")

    device_type = st.selectbox(
        "Qual dispositivo você está usando agora?",
        ["Celular", "Tablet", "Notebook", "Computador de mesa", "Outro"]
    )

    input_mode = st.selectbox(
        "Como você está digitando?",
        ["Teclado virtual", "Teclado físico", "Voz para texto", "Outro"]
    )

    st.divider()
    st.progress(0.45)
    st.markdown("### 3. Como foi seu dia?")

    wellbeing = deah_wellbeing_slider()

    st.divider()
    st.progress(0.60)
    st.markdown("### 4. Escalas afetivas")
    scale_help()
    st.info("No celular, toque e arraste somente quando quiser ajustar uma barrinha. Cada item aparece em um cartão separado para reduzir marcações acidentais durante a rolagem.")

    with st.expander("Dimensão negativa", expanded=True):
        negative_values = {}
        for key, label in NEGATIVE_ITEMS.items():
            negative_values[key] = deah_slider(label, f"neg_{key}")

    with st.expander("Dimensão positiva", expanded=True):
        positive_values = {}
        for key, label in POSITIVE_ITEMS.items():
            positive_values[key] = deah_slider(label, f"pos_{key}")

    st.divider()
    st.progress(0.78)
    st.markdown("### 5. Paisagem afetiva")

    image_metaphor = st.selectbox(
        "Qual paisagem se aproxima mais da forma como você percebe este momento?",
        list(METAPHOR_SCORE.keys())
    )

    st.divider()
    st.progress(0.90)
    st.markdown("### 6. Narrativa livre")

    feeling_text = st.text_area(
        "Como você está se sentindo hoje?",
        height=180,
        placeholder="Escreva livremente. Pode ser curto. O importante é que seja verdadeiro para você."
    )

    typing_duration_seconds = round(time.time() - st.session_state.diary_start_time, 2)
    typing_char_count = len(feeling_text)
    typing_word_count = count_words(feeling_text)
    typing_speed_cps = round(typing_char_count / typing_duration_seconds, 3) if typing_duration_seconds > 0 else 0

    if feeling_text.strip():
        st.caption(
            f"{typing_char_count} caracteres · {typing_word_count} palavras · tempo aproximado na tela: {typing_duration_seconds:.1f}s"
        )

    st.divider()
    st.progress(1.0)

    if st.button("✅ Salvar meu registro de hoje"):
        if not participant:
            st.error("ID mascarada não cadastrada.")
        elif not feeling_text.strip():
            st.error("Escreva uma narrativa livre antes de salvar.")
        else:
            row = {
                "participant_id": participant["id"],
                "day_number": int(day_number),
                "wellbeing": float(wellbeing),
                "feeling_text": feeling_text.strip(),
                "image_metaphor": image_metaphor,
                "device_type": device_type,
                "input_mode": input_mode,
                "typing_duration_seconds": typing_duration_seconds,
                "typing_char_count": typing_char_count,
                "typing_word_count": typing_word_count,
                "typing_speed_cps": typing_speed_cps
            }

            row.update({k: float(v) for k, v in negative_values.items()})
            row.update({k: float(v) for k, v in positive_values.items()})

            supabase.table("daily_entries").insert(row).execute()

            st.session_state.diary_start_time = time.time()
            st.success("Registro salvo com sucesso.")
            st.balloons()



elif page == "Pesquisador":
    st.header("🔬 Painel do Pesquisador")

    admin_password = st.secrets.get("DEAH_ADMIN_PASSWORD", "")
    if admin_password:
        typed_password = st.text_input("Senha do pesquisador", type="password")
        if typed_password != admin_password:
            st.info("Digite a senha para acessar o painel.")
            st.stop()
    else:
        st.warning("Painel sem senha. Para proteger, adicione DEAH_ADMIN_PASSWORD nos Secrets do Streamlit.")

    st.markdown("""
    Este painel ajuda a acompanhar a adesão ao diário de 7 dias e gerar
    uma lista simples de lembretes para envio manual por e-mail.
    """)

    participants_result = (
        supabase.table("participants")
        .select("*")
        .order("masked_id")
        .execute()
    )
    participants = participants_result.data or []

    entries_result = (
        supabase.table("daily_entries")
        .select("*")
        .execute()
    )
    entries = entries_result.data or []

    if not participants:
        st.info("Ainda não há participantes cadastrados.")
    else:
        entries_df = pd.DataFrame(entries) if entries else pd.DataFrame()
        rows = []

        for participant in participants:
            pid = participant.get("id")
            masked_id = participant.get("masked_id", "")
            current_day = calculate_current_day(participant)

            if not entries_df.empty and "participant_id" in entries_df.columns:
                p_entries = entries_df[entries_df["participant_id"] == pid].copy()
            else:
                p_entries = pd.DataFrame()

            answered_days = []
            last_answer = None

            if not p_entries.empty:
                if "day_number" in p_entries.columns:
                    answered_days = sorted(
                        pd.to_numeric(p_entries["day_number"], errors="coerce")
                        .dropna()
                        .astype(int)
                        .unique()
                        .tolist()
                    )

                date_cols = [c for c in ["created_at", "inserted_at", "updated_at"] if c in p_entries.columns]
                if date_cols:
                    last_answer = str(p_entries[date_cols[0]].dropna().max())
                elif "day_number" in p_entries.columns and answered_days:
                    last_answer = f"Dia {max(answered_days)}"

            answered_today = current_day in answered_days
            reminder_consent = bool(participant.get("reminder_consent", False))
            reminder_email = participant.get("reminder_email") or ""

            pending = reminder_consent and (1 <= current_day <= 7) and not answered_today

            rows.append({
                "ID mascarada": masked_id,
                "E-mail": reminder_email,
                "Aceitou lembrete": "sim" if reminder_consent else "não",
                "Dia atual": current_day,
                "Dias respondidos": ", ".join(map(str, answered_days)) if answered_days else "-",
                "Respondeu hoje": "sim" if answered_today else "não",
                "Última resposta": last_answer or "-",
                "Pendente hoje": "sim" if pending else "não"
            })

        monitor_df = pd.DataFrame(rows)

        total = len(monitor_df)
        pending_df = monitor_df[monitor_df["Pendente hoje"] == "sim"].copy()
        completed_today = (monitor_df["Respondeu hoje"] == "sim").sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("Participantes", total)
        col2.metric("Responderam hoje", int(completed_today))
        col3.metric("Lembretes pendentes", len(pending_df))

        st.markdown("### Pendentes para lembrar hoje")

        if pending_df.empty:
            st.success("Nenhum lembrete pendente hoje.")
        else:
            st.dataframe(pending_df, use_container_width=True)

            emails = [e for e in pending_df["E-mail"].dropna().astype(str).tolist() if e.strip()]
            st.text_area(
                "Copiar e-mails pendentes",
                value=", ".join(emails),
                height=90
            )

            link_deah = st.secrets.get("DEAH_APP_URL", "COLE_AQUI_O_LINK_DO_DEAH")
            message = f"""🌿 Olá!

Este é um lembrete do estudo DEAH.

Reserve 2 a 5 minutos para preencher o diário de hoje.

Acesse:
{link_deah}

Utilize sua ID mascarada cadastrada.

Obrigado pela sua participação!"""

            st.text_area("Mensagem padrão para copiar", value=message, height=190)

            csv_pending = pending_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Baixar lista de lembretes de hoje",
                csv_pending,
                "deah_lembretes_hoje.csv",
                "text/csv"
            )

        st.markdown("### Todos os participantes")
        st.dataframe(monitor_df, use_container_width=True)

        csv_all = monitor_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Baixar monitoramento completo",
            csv_all,
            "deah_monitoramento.csv",
            "text/csv"
        )

elif page == "Resultados":
    st.header("📊 Resultados")
    st.markdown("Visualize seus registros já salvos.")

    masked_id = st.text_input("ID mascarada para consultar resultados")

    if not masked_id.strip():
        st.info("Digite sua ID mascarada para visualizar os resultados.")
    else:
        participant = get_participant(masked_id)

        if not participant:
            st.error("Participante não encontrado.")
        else:
            result = (
                supabase.table("daily_entries")
                .select("*")
                .eq("participant_id", participant["id"])
                .order("day_number")
                .execute()
            )

            if not result.data:
                st.warning("Ainda não há respostas para esta ID.")
            else:
                df = pd.DataFrame(result.data)
                df = calculate_scores(df)
                ipa = calculate_ipa(df)

                st.markdown("### Resumo")
                col1, col2 = st.columns(2)
                col1.metric("Registros", len(df))
                col2.metric("IPA Global", ipa["ipa_global"])

                col3, col4 = st.columns(2)
                col3.metric("Afeto negativo médio", round(df["afeto_negativo"].mean(), 2))
                col4.metric("Afeto positivo médio", round(df["afeto_positivo"].mean(), 2))

                st.markdown("### Subíndices do IPA")
                ipa_df = pd.DataFrame({
                    "Subíndice": ["IPA-D", "IPA-T", "IPA-S", "IPA-V", "IPA-L"],
                    "Valor": [
                        ipa["ipa_d"], ipa["ipa_t"], ipa["ipa_s"], ipa["ipa_v"], ipa["ipa_l"]
                    ]
                })

                st.dataframe(ipa_df, use_container_width=True)
                st.bar_chart(ipa_df.set_index("Subíndice"))

                st.markdown("### Evolução afetiva")
                fig = px.line(
                    df,
                    x="day_number",
                    y=["afeto_negativo", "afeto_positivo", "desequilibrio_afetivo"],
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("### Bem-estar geral")
                fig2 = px.line(df, x="day_number", y="wellbeing", markers=True)
                st.plotly_chart(fig2, use_container_width=True)

                st.markdown("### Paisagens afetivas")
                st.bar_chart(df["image_metaphor"].value_counts())

                st.markdown("### Ecologia digital da resposta")

                if "device_type" in df.columns:
                    st.write("Dispositivos utilizados")
                    st.bar_chart(df["device_type"].fillna("Não informado").value_counts())

                if "input_mode" in df.columns:
                    st.write("Modos de entrada")
                    st.bar_chart(df["input_mode"].fillna("Não informado").value_counts())

                typing_cols = [
                    c for c in [
                        "day_number", "typing_char_count", "typing_word_count",
                        "typing_duration_seconds", "typing_speed_cps"
                    ]
                    if c in df.columns
                ]
                if typing_cols:
                    st.dataframe(df[typing_cols], use_container_width=True)

                st.markdown("### Nuvem de palavras")
                all_text = " ".join(df["feeling_text"].dropna().astype(str))
                words = clean_words(all_text)

                if words:
                    word_text = " ".join(words)
                    wc = WordCloud(width=1000, height=500, background_color="white").generate(word_text)

                    fig_wc, ax = plt.subplots(figsize=(10, 5))
                    ax.imshow(wc, interpolation="bilinear")
                    ax.axis("off")
                    st.pyplot(fig_wc)

                    freq = pd.Series(words).value_counts().reset_index()
                    freq.columns = ["palavra", "frequência"]
                    st.dataframe(freq, use_container_width=True)
                else:
                    st.info("Ainda não há texto suficiente para gerar a nuvem.")

                st.markdown("### Narrativas")
                st.dataframe(df[["day_number", "image_metaphor", "feeling_text"]], use_container_width=True)

                with st.expander("Dados completos"):
                    st.dataframe(df, use_container_width=True)

                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Baixar dados em CSV",
                    csv,
                    "deah_respostas.csv",
                    "text/csv"
                )
