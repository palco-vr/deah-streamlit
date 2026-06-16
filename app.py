import os
import re
import time
import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from wordcloud import WordCloud
import matplotlib.pyplot as plt

# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================

st.set_page_config(
    page_title="DEAH",
    page_icon="🌿",
    layout="wide"
)

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# ============================================================
# CONSTANTES DO INSTRUMENTO
# ============================================================

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
    "tension": "Tensão",
    "worry": "Preocupação",
    "restlessness": "Inquietação",
    "sadness": "Tristeza",
    "irritability": "Irritabilidade",
    "discouragement": "Desânimo"
}

POSITIVE_ITEMS = {
    "relaxation": "Relaxamento",
    "confidence": "Confiança",
    "serenity": "Serenidade",
    "joy": "Alegria",
    "patience": "Paciência",
    "hope": "Esperança"
}

STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os",
    "um", "uma", "com", "para", "por", "em", "no", "na", "nos", "nas",
    "que", "me", "eu", "hoje", "estou", "sinto", "sentindo", "muito",
    "mais", "menos", "foi", "era", "ser", "ter", "tem", "tive", "minha",
    "meu", "minhas", "meus", "isso", "essa", "esse", "também"
}

# Listas pareadas: 12 positivas e 12 negativas
POSITIVE_WORDS = {
    "calmo", "tranquilo", "feliz", "leve", "seguro", "confiante",
    "esperançoso", "organizado", "animado", "sereno", "acolhido", "alegre"
}

NEGATIVE_WORDS = {
    "ansioso", "medo", "triste", "cansado", "preocupado", "irritado",
    "tenso", "inquieto", "angustiado", "perdido", "pesado", "confuso"
}

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def get_participant(masked_id: str):
    result = (
        supabase.table("participants")
        .select("*")
        .eq("masked_id", masked_id.strip())
        .execute()
    )
    return result.data[0] if result.data else None


def clean_words(text: str):
    words = re.findall(r"\b[a-záàâãéèêíïóôõöúçñ]+\b", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def normalize(value, min_value, max_value):
    if max_value == min_value:
        return 0
    return max(0, min(100, ((value - min_value) / (max_value - min_value)) * 100))


def count_words(text: str) -> int:
    if not text:
        return 0
    return len(clean_words(text))


def calculate_scores(df: pd.DataFrame) -> pd.DataFrame:
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

    df["desequilibrio_afetivo"] = df[
        ["afeto_negativo", "positivo_invertido"]
    ].mean(axis=1)

    df["balanco_afetivo"] = df["afeto_positivo"] - df["afeto_negativo"]
    df["metaphor_score"] = df["image_metaphor"].map(METAPHOR_SCORE).fillna(5)

    return df


def calculate_ipa(df: pd.DataFrame) -> dict:
    if len(df) < 2:
        return {
            "ipa_global": 0,
            "ipa_d": 0,
            "ipa_t": 0,
            "ipa_s": 0,
            "ipa_v": 0,
            "ipa_l": 0
        }

    df = df.sort_values("day_number").copy()
    metaphors = df["image_metaphor"].tolist()
    scores = df["metaphor_score"].tolist()

    n = len(df)
    max_transitions = n - 1

    diversity = len(set(metaphors))
    transitions = sum(
        1 for i in range(1, n)
        if metaphors[i] != metaphors[i - 1]
    )

    # IPA-D: diversidade das paisagens
    ipa_d = normalize(diversity, 1, 7)

    # IPA-T: mobilidade/transição
    ipa_t = normalize(transitions, 0, max_transitions)

    # IPA-S: estabilidade
    volatility = transitions / max_transitions if max_transitions > 0 else 0
    ipa_s = (1 - volatility) * 100

    # IPA-V: direção vetorial da paisagem afetiva
    direction = scores[-1] - scores[0]
    ipa_v = normalize(direction, -9, 9)

    # IPA-L: linguagem afetiva emergente
    all_text = " ".join(df["feeling_text"].dropna().astype(str)).lower()
    words = clean_words(all_text)

    if words:
        positive_count = sum(1 for w in words if w in POSITIVE_WORDS)
        negative_count = sum(1 for w in words if w in NEGATIVE_WORDS)
        ipa_l = normalize(
            positive_count - negative_count,
            -len(words),
            len(words)
        )
    else:
        ipa_l = 50

    # Pesos iguais nesta versão psicométrica inicial
    ipa_global = (
        0.20 * ipa_d +
        0.20 * ipa_t +
        0.20 * ipa_s +
        0.20 * ipa_v +
        0.20 * ipa_l
    )

    return {
        "ipa_global": round(ipa_global, 2),
        "ipa_d": round(ipa_d, 2),
        "ipa_t": round(ipa_t, 2),
        "ipa_s": round(ipa_s, 2),
        "ipa_v": round(ipa_v, 2),
        "ipa_l": round(ipa_l, 2)
    }


def show_header_image():
    desktop_img = "assets/deah_abertura_desktop.png"
    mobile_img = "assets/deah_abertura_mobile.png"
    fallback_img = "assets/deah_abertura.png"

    for img in [desktop_img, fallback_img, mobile_img]:
        if os.path.exists(img):
            st.image(img, use_container_width=True)
            return


# ============================================================
# INTERFACE
# ============================================================

st.title("🌿 DEAH — Diário Ecológico de Ansiedade, Estresse e Humor")

menu = st.sidebar.radio(
    "Navegação",
    ["Início", "Participação", "Diário", "Resultados"]
)

# ============================================================
# INÍCIO
# ============================================================

if menu == "Início":
    show_header_image()

    st.markdown("""
    Bem-vindo(a).

    O **DEAH** é um instrumento digital experimental destinado ao acompanhamento
    longitudinal de experiências afetivas.

    Por meio de escalas breves, paisagens afetivas e narrativas livres, o sistema
    busca compreender como as experiências emocionais se organizam ao longo do tempo
    e em diferentes contextos da vida cotidiana.

    O preenchimento leva aproximadamente de **2 a 5 minutos** por dia.

    ---

    ### Participação voluntária

    Você está sendo convidado(a) a utilizar o DEAH — Diário Ecológico de Ansiedade,
    Estresse e Humor.

    O objetivo deste instrumento é acompanhar, ao longo do tempo, experiências afetivas,
    narrativas e paisagens emocionais por meio de breves registros diários.

    Sua participação é voluntária.

    Você pode deixar de responder qualquer pergunta, interromper um registro em andamento
    ou encerrar sua participação a qualquer momento, sem necessidade de justificativa.

    Os dados fornecidos serão utilizados exclusivamente para fins de pesquisa e
    desenvolvimento científico, sendo tratados de forma confidencial.

    Evite informar nomes completos, endereços ou outras informações que permitam sua
    identificação ou a identificação de terceiros.

    Este instrumento não realiza diagnóstico psicológico, psiquiátrico ou médico e não
    substitui acompanhamento profissional de saúde.

    Em caso de sofrimento intenso, procure apoio profissional ou serviço de saúde.

    ---

    ### Como começar

    1. Acesse **Participação**.
    2. Informe sua **ID mascarada**.
    3. Aceite voluntariamente participar.
    4. Depois acesse **Diário** e registre sua resposta diária.
    """)

# ============================================================
# PARTICIPAÇÃO
# ============================================================

if menu == "Participação":
    st.header("Participação")

    st.markdown("""
    Para participar, utilize uma **ID mascarada** fornecida pela pesquisa ou criada
    de forma que não identifique diretamente você.

    Ao marcar a opção abaixo, você declara que leu as informações da tela inicial e
    concorda livremente em participar.
    """)

    masked_id = st.text_input("ID mascarada")
    consent = st.checkbox("Li as informações e concordo voluntariamente em participar.")

    if st.button("Iniciar participação"):
        if not masked_id.strip():
            st.error("Informe uma ID mascarada.")
        elif not consent:
            st.error("O consentimento é obrigatório para iniciar.")
        elif get_participant(masked_id):
            st.warning("Essa ID já está cadastrada. Você já pode acessar o Diário.")
        else:
            supabase.table("participants").insert({
                "masked_id": masked_id.strip(),
                "consent": consent
            }).execute()
            st.success("Participação registrada com sucesso. Agora acesse o Diário.")

# ============================================================
# DIÁRIO
# ============================================================

if menu == "Diário":
    st.header("Entrada diária")

    if "diary_start_time" not in st.session_state:
        st.session_state.diary_start_time = time.time()

    masked_id = st.text_input("ID mascarada")
    participant = get_participant(masked_id) if masked_id.strip() else None

    if masked_id.strip() and not participant:
        st.warning("ID ainda não cadastrada. Acesse Participação primeiro.")

    day_number = st.number_input("Dia do diário", min_value=1, max_value=7, value=1)

    st.markdown("### Contexto de preenchimento")

    cdev1, cdev2 = st.columns(2)

    with cdev1:
        device_type = st.selectbox(
            "Qual dispositivo você está usando agora?",
            ["Celular", "Tablet", "Notebook", "Computador de mesa", "Outro"]
        )

    with cdev2:
        input_mode = st.selectbox(
            "Como você está digitando?",
            ["Teclado virtual", "Teclado físico", "Voz para texto", "Outro"]
        )

    st.markdown("---")
    st.markdown("### Escalas afetivas")
    st.caption("0 = nada | 1 = pouco | 2 = moderadamente | 3 = bastante | 4 = extremamente")

    col1, col2 = st.columns(2)

    negative_values = {}
    positive_values = {}

    with col1:
        st.markdown("#### Dimensão negativa")
        for key, label in NEGATIVE_ITEMS.items():
            negative_values[key] = st.slider(label, 0, 4, 0, key=f"neg_{key}")

    with col2:
        st.markdown("#### Dimensão positiva")
        for key, label in POSITIVE_ITEMS.items():
            positive_values[key] = st.slider(label, 0, 4, 0, key=f"pos_{key}")

    wellbeing = st.slider("Bem-estar geral", 0, 100, 50)

    st.markdown("---")
    st.markdown("### Paisagem afetiva")

    image_metaphor = st.selectbox(
        "Entre as paisagens abaixo, qual se aproxima mais da forma como você percebe este momento?",
        list(METAPHOR_SCORE.keys())
    )

    st.markdown("---")
    st.markdown("### Narrativa livre")

    feeling_text = st.text_area(
        "Como você está se sentindo hoje?",
        height=160,
        placeholder="Escreva livremente. Evite nomes completos ou informações que identifiquem pessoas."
    )

    typing_duration_seconds = round(time.time() - st.session_state.diary_start_time, 2)
    typing_char_count = len(feeling_text)
    typing_word_count = count_words(feeling_text)
    typing_speed_cps = round(
        typing_char_count / typing_duration_seconds,
        3
    ) if typing_duration_seconds > 0 else 0

    if feeling_text.strip():
        st.caption(
            f"Texto atual: {typing_char_count} caracteres | "
            f"{typing_word_count} palavras | "
            f"tempo aproximado na tela: {typing_duration_seconds:.1f}s"
        )

    if st.button("Salvar resposta"):
        if not participant:
            st.error("ID mascarada não cadastrada.")
        elif not feeling_text.strip():
            st.error("A narrativa livre é obrigatória nesta versão do DEAH.")
        else:
            row = {
                "participant_id": participant["id"],
                "day_number": int(day_number),
                "wellbeing": int(wellbeing),
                "feeling_text": feeling_text.strip(),
                "image_metaphor": image_metaphor,
                "device_type": device_type,
                "input_mode": input_mode,
                "typing_duration_seconds": typing_duration_seconds,
                "typing_char_count": typing_char_count,
                "typing_word_count": typing_word_count,
                "typing_speed_cps": typing_speed_cps
            }

            row.update({k: int(v) for k, v in negative_values.items()})
            row.update({k: int(v) for k, v in positive_values.items()})

            supabase.table("daily_entries").insert(row).execute()

            st.session_state.diary_start_time = time.time()
            st.success("Resposta salva com sucesso.")

# ============================================================
# RESULTADOS
# ============================================================

if menu == "Resultados":
    st.header("Resultados semanais")

    masked_id = st.text_input("Filtrar por ID mascarada")

    if not masked_id.strip():
        st.info("Informe uma ID mascarada para visualizar os resultados.")
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
                st.warning("Ainda não há respostas para este participante.")
            else:
                df = pd.DataFrame(result.data)
                df = calculate_scores(df)
                ipa = calculate_ipa(df)

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Respostas", len(df))
                col2.metric("Afeto negativo médio", round(df["afeto_negativo"].mean(), 2))
                col3.metric("Afeto positivo médio", round(df["afeto_positivo"].mean(), 2))
                col4.metric("IPA Global", ipa["ipa_global"])

                st.subheader("Subíndices do IPA")

                ipa_df = pd.DataFrame({
                    "Subíndice": ["IPA-D", "IPA-T", "IPA-S", "IPA-V", "IPA-L"],
                    "Valor": [
                        ipa["ipa_d"],
                        ipa["ipa_t"],
                        ipa["ipa_s"],
                        ipa["ipa_v"],
                        ipa["ipa_l"]
                    ]
                })

                st.dataframe(ipa_df, use_container_width=True)
                st.bar_chart(ipa_df.set_index("Subíndice"))

                st.subheader("Evolução afetiva")
                fig = px.line(
                    df,
                    x="day_number",
                    y=["afeto_negativo", "afeto_positivo", "desequilibrio_afetivo"],
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True)

                st.subheader("Balanço afetivo")
                fig_balance = px.line(
                    df,
                    x="day_number",
                    y="balanco_afetivo",
                    markers=True
                )
                st.plotly_chart(fig_balance, use_container_width=True)

                st.subheader("Bem-estar geral")
                fig2 = px.line(
                    df,
                    x="day_number",
                    y="wellbeing",
                    markers=True
                )
                st.plotly_chart(fig2, use_container_width=True)

                st.subheader("Frequência das paisagens afetivas")
                st.bar_chart(df["image_metaphor"].value_counts())

                st.subheader("Ecologia digital da resposta")

                if "device_type" in df.columns:
                    st.write("**Dispositivos utilizados**")
                    st.bar_chart(df["device_type"].fillna("Não informado").value_counts())

                if "input_mode" in df.columns:
                    st.write("**Modos de entrada**")
                    st.bar_chart(df["input_mode"].fillna("Não informado").value_counts())

                if "typing_word_count" in df.columns:
                    typing_cols = [
                        c for c in [
                            "day_number",
                            "typing_char_count",
                            "typing_word_count",
                            "typing_duration_seconds",
                            "typing_speed_cps"
                        ]
                        if c in df.columns
                    ]
                    st.dataframe(df[typing_cols], use_container_width=True)

                st.subheader("Nuvem de palavras")
                all_text = " ".join(df["feeling_text"].dropna().astype(str))
                words = clean_words(all_text)

                if words:
                    word_text = " ".join(words)

                    wc = WordCloud(
                        width=1000,
                        height=500,
                        background_color="white"
                    ).generate(word_text)

                    fig_wc, ax = plt.subplots(figsize=(10, 5))
                    ax.imshow(wc, interpolation="bilinear")
                    ax.axis("off")
                    st.pyplot(fig_wc)

                    freq = pd.Series(words).value_counts().reset_index()
                    freq.columns = ["palavra", "frequência"]
                    st.dataframe(freq, use_container_width=True)
                else:
                    st.info("Ainda não há texto suficiente para gerar a nuvem.")

                st.subheader("Respostas abertas")
                st.dataframe(
                    df[["day_number", "image_metaphor", "feeling_text"]],
                    use_container_width=True
                )

                st.subheader("Dados completos")
                st.dataframe(df, use_container_width=True)

                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Baixar dados em CSV",
                    csv,
                    "deah_respostas.csv",
                    "text/csv"
                )
