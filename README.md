# RAG Local

Estudia con tus apuntes en PDF usando una IA que corre en tu PC. Puedes **hacerle preguntas** al material, **resumir** cada PDF y **practicar** con preguntas tipo examen. Tus archivos no salen de tu computadora.

---

## Para qué sirve

| Uso | Ejemplo |
|---|---|
| **Preguntar sobre el material** | "¿Qué dice el teorema de Coase?", "Diferencia entre error tipo I y tipo II". La respuesta sale solo de tus PDFs y cita archivo y página. |
| **Resumir un PDF completo** | Notas por tema con definiciones, fórmulas y número de página. Se pueden copiar o descargar. |
| **Practicar para el examen** | Preguntas con respuesta modelo, de toda la materia o de un tema. Las respondes de memoria y marcas cuáles sabías. |
| **Ordenar por materia** | Cada materia tiene sus PDFs y solo busca en ellos. |

**Para qué no sirve:**
- **PDFs escaneados** (fotos sin texto seleccionable): la app los detecta y avisa. Antes de subirlos, pásalos por un OCR, por ejemplo Adobe Scan, Google Drive → "Abrir con Documentos" u `ocrmypdf`.
- **Gráficos y diagramas**: solo lee el texto, no las imágenes.
- **Reemplazar la lectura**: el modelo acierta la gran mayoría de las veces, pero puede equivocarse. Por eso siempre muestra la página de donde sacó la información.

---

## Requisitos mínimos

| | Mínimo | Recomendado | Probado en |
|---|---|---|---|
| **Sistema** | Windows 10/11, Linux o macOS | | Windows 11 |
| **RAM** | 16 GB | 16 GB o más, con pocas apps abiertas | 16 GB |
| **GPU** | No obligatoria (sin GPU funciona, pero mucho más lento) | NVIDIA con 6 GB de VRAM o más | RTX 4050 Laptop, 6 GB |
| **Disco libre** | 8 GB (modelos + dependencias) + tus PDFs | | |
| **Software** | [Python 3.10+](https://www.python.org/downloads/), [Node.js 18+](https://nodejs.org), [Ollama](https://ollama.com) | | Python 3.14, Node 24 |

> Con 8 GB de RAM no está probado. Debería funcionar con un modelo más chico: `ollama pull qwen2.5:3b` y `OLLAMA_MODEL=qwen2.5:3b` en `backend/.env`. Es más rápido, pero responde peor.
>
> Linux y macOS no están probados. Todo lo que usa la app es multiplataforma; los comandos para esos sistemas están indicados abajo.

**Tiempos medidos en el equipo de prueba:**

| Acción | Tiempo |
|---|---|
| Procesar un PDF al subirlo | ~2 s cada 10 páginas |
| Responder una pregunta | 5–10 s (la primera tras un rato sin uso, +20 s mientras carga el modelo) |
| Generar 5 preguntas de práctica | 25–40 s |
| Resumir | ~35 s por página de apunte denso; bastante menos en diapositivas. 30 páginas ≈ 15–20 min, en segundo plano |

---

## Instalación (una sola vez)

**1. Descarga los modelos de IA** (~5 GB). Con Ollama instalado y abierto:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

**2. Instala el backend:**

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # Linux/macOS: cp .env.example .env
```

**3. Instala el frontend:**

```bash
cd frontend
npm install
copy .env.example .env         # Linux/macOS: cp .env.example .env
```

---

## Uso

**Iniciar** (con Ollama abierto):

- **Windows**: `.\start-all.ps1` abre dos ventanas: backend y frontend. Para detener la app, ciérralas.
- **Linux/macOS**: `./start-all.sh` (Ctrl+C para detener).

Luego abre **http://localhost:5173**.

**Paso a paso:**

1. **Crea una materia** con el botón **+** (arriba a la izquierda).
2. **Sube los PDFs** arrastrándolos al recuadro. Puedes subir varios a la vez; cada uno tarda unos segundos en procesarse.
3. Elige una pestaña:
   - **Preguntar**: escribe y presiona Enter. Con "Buscar en" puedes limitar la búsqueda a un solo PDF. En **Fuentes**, debajo del chat, se ven los fragmentos usados.
   - **Resúmenes**: elige un PDF y presiona **Resumir**. Puedes seguir usando la app mientras tanto.
   - **Practicar**: elige el material, opcionalmente un tema, y presiona **Generar**. Responde mentalmente, presiona **Ver respuesta** y marca "La sabía" o "Repasar".

---

## Cómo sacarle el máximo provecho

**Al cargar el material**
- **Una materia por asignatura.** Si mezclas materias, las respuestas también se mezclan.
- **Solo PDFs con texto seleccionable.** Si al lado del PDF aparece "N sin texto", esas páginas son imágenes: pásalas por un OCR y vuelve a subir el archivo.

**Al preguntar**
- **Haz preguntas concretas y usa las palabras del apunte.** "¿Qué es un bien de Giffen?" funciona mejor que "explicame la unidad 1".
- **Formatos que funcionan bien:** "¿Qué es…?", "Diferencia entre… y…", "¿Por qué…?", "¿Cuándo se usa…?", "Explícame… con el ejemplo del apunte".
- **Repregunta en la misma conversación** ("¿y en el largo plazo?"): recuerda lo anterior. Usa **Nueva** cuando cambies de tema.
- **Si responde "No encontré esa información"**, prueba con otras palabras o elige el PDF en "Buscar en". Si sigue igual, probablemente no esté en el material: el modelo está configurado para no inventar.
- **Las preguntas que abarcan toda la materia** ("¿qué temas entran?") no funcionan bien en el chat, porque solo lee unos pocos fragmentos por pregunta. Para eso están los resúmenes.
- **Verifica en la página citada** las fórmulas, los números y todo lo que vayas a escribir en un examen.

**Resúmenes**
- **Genéralos con tiempo** (por ejemplo, mientras haces otra cosa) y solo de los PDFs que vas a estudiar.
- **Durante los resúmenes largos, mantén la laptop enchufada y sin suspensión.** Si se suspende, el resumen se pausa hasta que vuelva.
- **Descárgalos** (`.md`) para tenerlos fuera de la app.

**Práctica**
- **Primero repasa toda la materia** sin tema: las preguntas se reparten por todo el material.
- **Después practica por tema** con lo que marcaste "Repasar".
- **Responde de verdad** (en voz alta o en papel) antes de ver la respuesta.

**Rendimiento**
- **Cierra las apps pesadas** (por ejemplo, el navegador con muchas pestañas): el modelo necesita unos 5 GB de memoria.
- **El modelo queda cargado 30 minutos** tras la última pregunta. Si tu PC tiene poca RAM, baja `OLLAMA_KEEP_ALIVE` a `5m` en `backend/.env`.

---

## Problemas frecuentes

| Problema | Solución |
|---|---|
| "Sin backend" arriba a la derecha | El backend no está corriendo. Ábrelo con `.\start-all.ps1` (o `cd backend` y `venv\Scripts\python app.py`). |
| "Sin Ollama" | Abre Ollama, o ejecuta `ollama serve`. |
| "Falta un modelo" | El aviso indica qué `ollama pull …` ejecutar. |
| Un PDF queda en "No se pudo procesar" | Probablemente esté escaneado. El mensaje debajo del nombre explica qué hacer. |
| Todo va muy lento o la PC se traba | Falta RAM: cierra otras apps, o ejecuta `ollama stop qwen2.5:7b` para liberarla al instante. |

---

## Configuración

Las opciones están en `backend/.env`. Las que más vale la pena tocar:

| Variable | Valor por defecto | Para qué |
|---|---|---|
| `OLLAMA_MODEL` | `qwen2.5:7b` | Modelo que responde. `qwen2.5:3b` es más liviano. |
| `OLLAMA_KEEP_ALIVE` | `30m` | Cuánto tiempo queda el modelo en memoria tras usarlo. |
| `MAX_UPLOAD_SIZE_MB` | `50` | Tamaño máximo por PDF. |

> Se eligió `qwen2.5:7b` en lugar de `mistral` después de compararlos con las mismas preguntas. Ante preguntas cuya respuesta no estaba en los apuntes, mistral inventó una respuesta en 2 de 4 casos (una de ellas incorrecta); qwen no inventó ninguna. Además, responde casi el doble de rápido.

Tus datos se guardan en `backend/data/` (la base `rag.db` y los PDFs subidos). Para hacer una copia de seguridad, copia esa carpeta.

---

## Para desarrolladores

- **Stack:** Flask + SQLite (backend), React + TypeScript + Vite (frontend), Ollama (`qwen2.5:7b` para generar texto y `nomic-embed-text` para embeddings).
- **Tests:** `cd backend && venv\Scripts\python -m pytest` (42 tests, con Ollama simulado). Para el frontend, `npm run build` hace el type-check.
- **Código:** `backend/services/` contiene la lógica: `pdf_processor`, `embeddings`, `rag` (chat) y `study` (resúmenes y preguntas). `backend/routes/` contiene la API REST bajo `/api`.
