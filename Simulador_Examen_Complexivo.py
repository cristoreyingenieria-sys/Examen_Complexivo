import json
import random
import re
import google.generativeai as genai
import pypdf
import streamlit as st

# Configuración de la página
st.set_page_config(
    page_title="Simulador de Examen Complexivo",
    layout="wide",
    initial_sidebar_state="expanded",
)


def generar_distractores_gemini(enunciado, respuesta_correcta, api_key):
    """Consulta a Gemini para obtener 3 distractores verosímiles."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = f"""
        Dado el siguiente enunciado y su respuesta correcta, genera exactamente 3 respuestas incorrectas (distractores) que sean coherentes y verosímiles sobre el mismo tema académico.
        No mezcles información irrelevante ni inventes datos sin sentido.
        
        Pregunta: {enunciado}
        Respuesta Correcta: {respuesta_correcta}
        
        Responde ÚNICAMENTE con un JSON válido en este formato estricto:
        {{"distractores": ["Opción falsa 1", "Opción falsa 2", "Opción falsa 3"]}}
        """

        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.4,
            },
        )
        data = json.loads(response.text)
        return data.get("distractores", [])
    except Exception:
        return [
            "Opción alternativa no correspondiente",
            "Concepto no aplicable al contexto",
            "Criterio secundario no relevante",
        ]


def procesar_pdf_completo(pdf_file, api_key):
    """Extrae la totalidad de las preguntas del PDF."""
    reader = pypdf.PdfReader(pdf_file)
    texto_total = ""

    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            texto_total += "\n" + txt

    bloques = re.split(r"\n(?=\d{1,4}[\.\)]\s+)", texto_total)

    preguntas_procesadas = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_bloques = len(bloques)

    for i, bloque in enumerate(bloques):
        bloque = bloque.strip()
        if not bloque:
            continue

        match_num = re.match(r"^(\d{1,4})[\.\)]\s*(.*)", bloque, re.DOTALL)
        if not match_num:
            continue

        num_pregunta = match_num.group(1)
        contenido = match_num.group(2).strip()

        status_text.text(
            f"Procesando pregunta {num_pregunta} de {total_bloques}..."
        )
        progress_bar.progress(min((i + 1) / total_bloques, 1.0))

        es_opcion_multiple = bool(
            re.search(r"[A-D]\)\s+", contenido)
            and re.search(r"Respuesta(?:\s+correcta)?:", contenido, re.IGNORECASE)
        )

        if es_opcion_multiple:
            partes = re.split(r"[A-D]\)\s+", contenido, maxsplit=1)
            enunciado = partes[0].strip()

            opciones_raw = re.findall(
                r"([A-D])\)\s*(.*?)(?=\s*[A-D]\)|\s*(?:✓\s*)?Respuesta|\Z)",
                contenido,
                re.DOTALL,
            )

            dict_opciones = {
                opt[0]: opt[1].strip().replace("\n", " ") for opt in opciones_raw
            }

            match_resp = re.search(
                r"(?:✓\s*)?Respuesta(?:\s+correcta)?:\s*([A-D])",
                contenido,
                re.IGNORECASE,
            )
            letra_correcta = match_resp.group(1).upper() if match_resp else "A"
            texto_correcto = dict_opciones.get(
                letra_correcta, list(dict_opciones.values())[0]
            )
            lista_opciones = list(dict_opciones.values())

            preguntas_procesadas.append({
                "numero": num_pregunta,
                "enunciado": enunciado,
                "opciones": lista_opciones,
                "respuesta_correcta": texto_correcto,
            })

        else:
            partes = re.split(
                r"Respuesta:\s*", contenido, flags=re.IGNORECASE, maxsplit=1
            )
            enunciado = partes[0].strip()
            respuesta_correcta = partes[1].strip() if len(partes) > 1 else ""
            respuesta_correcta = re.sub(r"\n.*", "", respuesta_correcta).strip()

            distractores = generar_distractores_gemini(
                enunciado, respuesta_correcta, api_key
            )

            todas_opciones = [respuesta_correcta] + distractores[:3]
            while len(todas_opciones) < 4:
                todas_opciones.append(
                    f"Opción alternativa {len(todas_opciones)}"
                )

            random.shuffle(todas_opciones)

            preguntas_procesadas.append({
                "numero": num_pregunta,
                "enunciado": enunciado,
                "opciones": todas_opciones,
                "respuesta_correcta": respuesta_correcta,
            })

    status_text.text("¡Procesamiento completo finalizado!")
    progress_bar.empty()
    return preguntas_procesadas


def seleccionar_examen_aleatorio(banco_completo, cantidad=100):
    """Selecciona N preguntas aleatorias del banco total cargado."""
    num_a_seleccionar = min(cantidad, len(banco_completo))
    return random.sample(banco_completo, num_a_seleccionar)


def main():
    st.title("Simulador de Examen Complexivo")
    st.write(
        "Carga tu cuestionario PDF. El sistema seleccionará **100 preguntas aleatorias** para cada intento de evaluación."
    )

    st.sidebar.header("Configuración")
    api_key = st.sidebar.text_input(
        "Ingresa tu Google Gemini API Key:",
        type="password",
        autocomplete="new-password",
    )
    st.sidebar.markdown(
        "[Consigue tu API Key gratuita en Google AI Studio](https://aistudio.google.com/)"
    )

    uploaded_file = st.file_uploader(
        "Carga el archivo PDF con las preguntas", type=["pdf"]
    )

    if uploaded_file and api_key:
        if "banco_completo" not in st.session_state:
            if st.button("Procesar Cuestionario PDF"):
                with st.spinner("Procesando banco completo de preguntas..."):
                    st.session_state.banco_completo = procesar_pdf_completo(
                        uploaded_file, api_key
                    )
                    # Seleccionar las primeras 100 aleatorias
                    st.session_state.examen_actual = (
                        seleccionar_examen_aleatorio(
                            st.session_state.banco_completo, 100
                        )
                    )
                st.rerun()

    elif uploaded_file and not api_key:
        st.warning(
            "Por favor, ingresa tu API Key de Gemini en la barra lateral para continuar."
        )

    # Si el banco ya está procesado, mostramos la interfaz del simulacro
    if "banco_completo" in st.session_state:
        st.sidebar.markdown("---")
        st.sidebar.write(
            f"**Banco total:** {len(st.session_state.banco_completo)} preguntas"
        )

        # Botón para barajar y sacar un nuevo grupo de 100
        if st.sidebar.button("🔀 Generar nuevo examen (100 aleatorias)"):
            st.session_state.examen_actual = seleccionar_examen_aleatorio(
                st.session_state.banco_completo, 100
            )
            st.rerun()

        preguntas_examen = st.session_state.examen_actual
        st.success(
            f"Examen generado con **{len(preguntas_examen)} preguntas aleatorias**."
        )

        with st.form("formulario_examen"):
            respuestas_usuario = {}

            for idx, p in enumerate(preguntas_examen):
                st.markdown(f"### Pregunta {idx + 1} (N° {p['numero']})")
                st.write(p["enunciado"])

                key_unica = f"radio_{idx}_{p['numero']}"

                respuestas_usuario[idx] = st.radio(
                    "Selecciona tu respuesta:",
                    options=p["opciones"],
                    key=key_unica,
                )
                st.markdown("---")

            submit_button = st.form_submit_button(
                "Finalizar y Calificar Simulacro"
            )

        if submit_button:
            aciertos = 0
            total = len(preguntas_examen)

            st.header("Resultados de la Evaluación")

            for idx, p in enumerate(preguntas_examen):
                num_original = p["numero"]
                resp_user = respuestas_usuario.get(idx)
                resp_correcta = p["respuesta_correcta"]

                if resp_user == resp_correcta:
                    aciertos += 1
                else:
                    st.error(
                        f"**Pregunta {idx + 1} (Original N° {num_original}): Incorrecta**"
                    )
                    st.write(f"**Enunciado:** {p['enunciado']}")
                    st.write(f"Tu respuesta: {resp_user}")
                    st.write(f"Respuesta correcta: {resp_correcta}")
                    st.markdown("---")

            puntaje = (aciertos / total) * 10
            st.balloons()
            st.metric(
                label="Calificación Final",
                value=f"{puntaje:.2f} / 10",
                delta=f"{aciertos} aciertos de {total} preguntas",
            )


if __name__ == "__main__":
    main()