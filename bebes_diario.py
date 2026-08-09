import os
import random
import json
import re
import time
import base64
import urllib.parse
import requests
from groq import Groq
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- CONFIGURAÇÕES ---
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY")
BLOGGER_ID        = os.environ.get("BLOGGER_ID_BEBES")
CLIENT_ID         = os.environ.get("BLOGGER_CLIENT_ID")
CLIENT_SECRET     = os.environ.get("BLOGGER_CLIENT_SECRET")
REFRESH_TOKEN     = os.environ.get("BLOGGER_REFRESH_TOKEN")
POLLINATIONS_TOKEN = os.environ.get("POLLINATIONS_TOKEN")  # opcional: remove marca dagua e aumenta limite
# Sem token: 1 requisicao a cada 15s. Com token gratuito (auth.pollinations.ai): a cada 5s.
INTERVALO_POLLINATIONS = 6 if POLLINATIONS_TOKEN else 16
IMGBB_API_KEY     = os.environ.get("IMGBB_API_KEY")  # hospedagem permanente das imagens

for nome, valor in [
    ("GROQ_API_KEY",          GROQ_API_KEY),
    ("BLOGGER_ID_BEBES",      BLOGGER_ID),
    ("BLOGGER_CLIENT_ID",     CLIENT_ID),
    ("BLOGGER_CLIENT_SECRET", CLIENT_SECRET),
    ("BLOGGER_REFRESH_TOKEN", REFRESH_TOKEN),
]:
    if not valor:
        raise ValueError(f"Faltou configurar a variável/segredo: {nome}")

if not IMGBB_API_KEY:
    print("⚠️  IMGBB_API_KEY não configurada — imagens geradas via IA serão embed como base64 (fallback).")

groq_client = Groq(api_key=GROQ_API_KEY)
MODELO_IA   = "llama-3.3-70b-versatile"

# ─────────────────────────────────────────────
#  LISTA DE TEMAS — cuidados com bebês e crianças pequenas
# ─────────────────────────────────────────────
TEMAS = [
    {"nome": "Como fazer o bebê arrotar",           "img_en": "parent gently burping newborn baby over shoulder, illustration"},
    {"nome": "Cólica do recém-nascido",              "img_en": "baby crying colic tummy discomfort, illustration"},
    {"nome": "Soluços do bebê",                      "img_en": "baby with hiccups calm parent holding, illustration"},
    {"nome": "Primeiro banho do recém-nascido",      "img_en": "newborn baby bath time gentle care, illustration"},
    {"nome": "Como trocar a fralda corretamente",    "img_en": "parent changing baby diaper nursery, illustration"},
    {"nome": "Quando trocar a fralda (frequência)",  "img_en": "diaper changing station nursery supplies, illustration"},
    {"nome": "Assaduras e cuidados com a pele",      "img_en": "baby skincare gentle cream nursery, illustration"},
    {"nome": "Cuidados com o coto umbilical",        "img_en": "newborn baby belly button care, illustration"},
    {"nome": "Amamentação: pega correta",            "img_en": "mother breastfeeding baby cozy nursery, illustration"},
    {"nome": "Mamadeira: como preparar com segurança","img_en": "baby bottle preparation kitchen safe, illustration"},
    {"nome": "Introdução alimentar (papinhas)",      "img_en": "baby first foods high chair colorful, illustration"},
    {"nome": "Sono do bebê: rotina e segurança",     "img_en": "baby sleeping safely crib nursery, illustration"},
    {"nome": "Choro do bebê: entendendo os sinais",  "img_en": "parent comforting crying baby, illustration"},
    {"nome": "Enxoval essencial para recém-nascido", "img_en": "baby essentials layette nursery items, illustration"},
    {"nome": "O que levar na bolsa maternidade",     "img_en": "diaper bag essentials packed neatly, illustration"},
    {"nome": "Montando o quarto do bebê",            "img_en": "cozy nursery room crib decoration, illustration"},
    {"nome": "Primeiros dentes do bebê",             "img_en": "baby teething toy gentle smile, illustration"},
    {"nome": "Calendário de vacinação infantil",     "img_en": "pediatrician checkup baby vaccine schedule, illustration"},
    {"nome": "Desenvolvimento motor por idade",      "img_en": "baby tummy time crawling milestone, illustration"},
    {"nome": "Segurança em casa para bebês",         "img_en": "childproof home safety nursery, illustration"},
    {"nome": "Passeando com o bebê pela primeira vez","img_en": "parent stroller walk park baby, illustration"},
    {"nome": "Roupinhas certas para cada estação",   "img_en": "baby clothes seasonal folded nursery, illustration"},
    {"nome": "Como economizar com o bebê",           "img_en": "budget friendly baby items savings, illustration"},
    {"nome": "Itens essenciais dos primeiros meses", "img_en": "newborn must have items flat lay, illustration"},
    {"nome": "Brincadeiras por faixa etária",        "img_en": "baby playing toys tummy time, illustration"},
    {"nome": "Febre no bebê: quando se preocupar",   "img_en": "parent checking baby temperature thermometer, illustration"},
    {"nome": "Resfriado e nariz entupido do bebê",   "img_en": "baby nasal aspirator gentle care, illustration"},
    {"nome": "Chupeta: usar ou não usar",            "img_en": "baby pacifier calm sleeping, illustration"},
    {"nome": "Sono seguro: berço e posição certa",   "img_en": "safe crib sleep position baby, illustration"},
    {"nome": "Teste do pezinho e exames do bebê",    "img_en": "newborn hospital checkup nurse, illustration"},
    {"nome": "Higiene bucal desde cedo",             "img_en": "baby gum cleaning soft brush, illustration"},
    {"nome": "Cortando as unhas do bebê com segurança","img_en": "trimming baby nails carefully, illustration"},
    {"nome": "Protetor solar e sol para bebês",      "img_en": "baby sun hat shade stroller, illustration"},
    {"nome": "Transporte seguro: bebê conforto e cadeirinha","img_en": "baby car seat installed safely, illustration"},
    {"nome": "Voltando ao trabalho: rotina com o bebê","img_en": "working parent balancing baby schedule, illustration"},
    {"nome": "Cuidados com bebês prematuros",        "img_en": "premature baby incubator gentle care, illustration"},
    {"nome": "Irmãos mais velhos e a chegada do bebê","img_en": "older sibling meeting new baby, illustration"},
    {"nome": "Rotina noturna para dormir melhor",    "img_en": "bedtime routine baby lullaby, illustration"},
]

ARQUIVO_HISTORICO = "historico_bebes.txt"
IMAGEM_PADRAO     = "https://upload.wikimedia.org/wikipedia/commons/thumb/9/95/News_icon.svg/640px-News_icon.svg.png"

# Máx de posts recentes que ficam na "lista negra" (evita repetição)
JANELA_ANTIREPETIÇÃO = 8


# ─────────────────────────────────────────────
#  HISTÓRICO — anti-repetição aleatório
# ─────────────────────────────────────────────
def carregar_historico():
    if not os.path.exists(ARQUIVO_HISTORICO):
        return []
    with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def marcar_tema_usado(nome_tema):
    with open(ARQUIVO_HISTORICO, "a", encoding="utf-8") as f:
        f.write(nome_tema + "\n")


def escolher_tema():
    """
    Escolhe aleatoriamente, evitando repetir os últimos JANELA_ANTIREPETIÇÃO temas.
    Garante que nenhum tema se repita até o ciclo ser suficientemente longo.
    """
    historico   = carregar_historico()
    recentes    = set(historico[-JANELA_ANTIREPETIÇÃO:])
    disponiveis = [t for t in TEMAS if t["nome"] not in recentes]

    # Se todos estiverem "bloqueados" (lista pequena), libera todos
    if not disponiveis:
        disponiveis = TEMAS

    escolhido = random.choice(disponiveis)
    print(f"🎲 Tema escolhido: {escolhido['nome']}")
    return escolhido


# ─────────────────────────────────────────────
#  GROQ (texto)
# ─────────────────────────────────────────────
def pedir_ia_groq(prompt, temperatura=0.75):
    response = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODELO_IA,
        temperature=temperatura,
    )
    return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────
#  TÍTULO — anti-repetição forçada
# ─────────────────────────────────────────────
def gerar_titulo(tema):
    historico = carregar_historico()
    titulos_recentes = historico[-20:] if len(historico) >= 20 else historico

    prompt = (
        f"Crie um título de blog original, acolhedor, empático e otimizado para SEO, "
        f"em português do Brasil, sem aspas, sobre o tema '{tema}' voltado para pais e mães "
        f"de bebês e crianças pequenas.\n"
        f"IMPORTANTE: O título DEVE ser diferente e criativo — não pode ser parecido com nenhum destes já usados recentemente:\n"
        f"{chr(10).join(titulos_recentes) if titulos_recentes else '(nenhum ainda)'}\n\n"
        f"Use ângulos diferentes: pode focar em guia passo a passo, dúvidas comuns de pais "
        f"de primeira viagem, dicas que os pediatras recomendam, erros comuns a evitar, "
        f"curiosidades sobre o desenvolvimento do bebê, etc.\n"
        f"Responda apenas o título, texto puro."
    )
    return pedir_ia_groq(prompt, temperatura=0.85).replace('"', '').strip()


# ─────────────────────────────────────────────
#  MARCADORES (labels reais do Blogger, não texto solto no artigo)
# ─────────────────────────────────────────────
def gerar_tags(tema, titulo):
    prompt = f"""
Gere de 4 a 6 marcadores (tags) curtos, em português do Brasil, para um post de blog de
maternidade/paternidade sobre o tema "{tema}", com título "{titulo}".
Cada marcador deve ter 1 a 3 palavras, útil para categorização e SEO no Blogger
(ex: "cuidados com bebê", "recém-nascido", "pais de primeira viagem", "maternidade real").
Retorne APENAS um array JSON de strings, nada mais.
Exemplo: ["marcador um", "marcador dois", "marcador tres"]
"""
    raw = pedir_ia_groq(prompt, temperatura=0.5)
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if match:
        try:
            tags = json.loads(match.group())
            if isinstance(tags, list):
                limpo = [str(t).strip() for t in tags if str(t).strip()]
                if limpo:
                    return limpo[:6]
        except Exception:
            pass
    # Fallback: garante que sempre vai ao menos 1 marcador, nunca fica vazio
    return [tema]


# ─────────────────────────────────────────────
#  ÂNGULOS — variedade de abordagem
# ─────────────────────────────────────────────
ANGULOS = [
    "Guia completo passo a passo para pais de primeira viagem, com dicas práticas e acolhedoras.",
    "Desmistificando mitos e crendices populares sobre o tema, com base no que pediatras realmente recomendam.",
    "Foco em como entender os sinais do bebê e responder com calma e confiança.",
    "Curiosidades sobre o desenvolvimento do bebê que poucos pais conhecem e que ajudam a entender melhor essa fase.",
    "Guia prático de economia: como fazer bem com pouco, sem abrir mão do essencial para o bebê.",
    "Os erros mais comuns que pais cometem (sem saber!) e como corrigir com tranquilidade.",
    "Tudo sobre quando procurar o pediatra: sinais de alerta e o que pode esperar em casa com calma.",
    "Como montar uma rotina que funcione para a família inteira, com realismo (sem prometer perfeição).",
]

# Variações do segmento do diário pessoal
MODOS_DIARIO = [
    # Vai direto sem apresentar a família
    "direto",
    # Apresenta brevemente só no contexto da história
    "contexto_rapido",
]


# ─────────────────────────────────────────────
#  ARTIGO
# ─────────────────────────────────────────────
def gerar_artigo_cuidados(tema, num_imagens):
    angulo = random.choice(ANGULOS)
    modo_diario = random.choice(MODOS_DIARIO)

    # Histórico de situações já contadas (evita repetição no diário)
    historico = carregar_historico()
    situacoes_recentes = historico[-15:] if len(historico) >= 15 else historico
    aviso_situacoes = (
        f"SITUAÇÕES JÁ CONTADAS RECENTEMENTE (NÃO repita nenhuma dessas):\n"
        f"{', '.join(situacoes_recentes) if situacoes_recentes else '(nenhuma ainda)'}\n"
    ) if situacoes_recentes else ""

    if modo_diario == "direto":
        instrucao_diario = (
            "No segmento do diário pessoal, vá DIRETO para a história sem apresentar "
            "Aurora ou Davi — quem lê o blog já os conhece de cor. Comece já na cena, "
            "como se fosse um episódio de uma série que o leitor acompanha."
        )
    else:
        instrucao_diario = (
            "No segmento do diário pessoal, mencione o nome da criança envolvida de forma "
            "casual, dentro do contexto da história — sem aquela introdução formal de "
            "'tenho uma filha chamada...'. Quem acompanha o blog já sabe quem são."
        )

    marcadores_instrucao = ""
    if num_imagens > 1:
        marcadores_instrucao = (
            f"\nO artigo terá {num_imagens - 1} imagem(ns) além da capa. "
            f"Insira os marcadores <!--IMG_2-->, <!--IMG_3-->"
            + (f", <!--IMG_{num_imagens}-->" if num_imagens > 3 else "")
            + f" em momentos narrativos naturais (após parágrafos, antes de nova seção h2). "
            f"Não coloque dois marcadores seguidos.\n"
        )

    prompt = f"""
Você é o autor de um blog de maternidade e paternidade muito querido, com persona acolhedora,
empática e bem-humorada. Escreve como aquela amiga/amigo experiente que já passou por tudo isso
e conta as coisas de um jeito leve, sem ser alarmista ou didático demais. Usa comparações que
fazem sentido no dia a dia, conta histórias reais da rotina e sempre tranquiliza o leitor.
Tem uma filha bebê chamada Aurora (curiosa, cheia de energia, especialista em fazer bagunça na
hora errada) e um filho mais velho, Davi (o "ajudante caçula-chefe", cheio de ideias e perguntas).

TEMA DO DIA: {tema}

ÂNGULO OBRIGATÓRIO PARA ESTE ARTIGO:
"{angulo}"

Use esse ângulo como fio condutor do artigo inteiro. Não é só um tópico — é a perspectiva
de toda a matéria.

REGRAS DE CONTEÚDO:
- NÃO seja genérico. As orientações têm que ser específicas para o tema "{tema}".
- Inclua CURIOSIDADES sobre desenvolvimento infantil ou fisiologia do bebê relacionadas ao
  tema — coisas que a maioria dos pais de primeira viagem não sabe.
- Tom: acolhedor, tranquilizador, com um toque de humor leve sobre as trapalhadas da rotina
  com bebê. Nunca alarmista, nunca faz o leitor se sentir culpado ou incompetente.
- Ao falar de saúde, sintomas ou qualquer situação que exija avaliação médica, oriente sempre
  a procurar o pediatra. NÃO dê diagnósticos, doses de medicamento ou instruções de emergência
  médica — apenas oriente a buscar orientação profissional. Não invente dados.
- Tamanho do conteúdo de dicas: entre 900 e 1300 palavras.
- PROIBIDO repetir a mesma ideia em parágrafos diferentes com outras palavras.
{marcadores_instrucao}
REGRAS DE FORMATO (HTML puro, sem Markdown):
1. Parágrafo de abertura (<p>) envolvente que entra no ângulo já de cara, sem rodeios.
2. NO MÍNIMO 4 subtítulos <h2> cobrindo aspectos diferentes do ângulo escolhido.
3. Pelo menos 1 lista <ul> com dicas práticas e específicas.
4. 2 a 3 <blockquote> com comentários leves e acolhedores, tipo recado de mãe/pai experiente.
5. NÃO inclua uma lista de tags/marcadores no final do texto — isso é gerado separadamente.

Depois do conteúdo principal, adicione:
<h2>Diário da Semana 👶</h2>
{instrucao_diario}
Escreva 2 parágrafos grandes, no estilo diário pessoal bem-humorado e acolhedor sobre a rotina
com os filhos. A cena deve ser NOVA, cotidiana e específica — uma trapalhada, um momento fofo,
uma coisa que só quem tem filho pequeno entende.
{aviso_situacoes}
O humor pode ser auto-depreciativo (do narrador sobre o próprio cansaço/aprendizado), mas
sempre carinhoso e respeitoso com as crianças.
"""
    return pedir_ia_groq(prompt, temperatura=0.82)


# ─────────────────────────────────────────────
#  PROMPTS DE IMAGEM (via Groq)
# ─────────────────────────────────────────────
def gerar_prompts_imagens(tema, titulo, num_imagens):
    outros = ""
    if num_imagens > 1:
        outros = (
            f"\n- Objetos 2 a {num_imagens}: cenas conceituais e emocionais que ilustram "
            f"momentos de cuidado, carinho ou aprendizado relacionados a '{tema}'. "
            f"Cada uma deve ser visualmente única e transmitir uma emoção diferente."
        )

    prompt = f"""
You are an art director creating image prompts AND captions for a warm, gentle
parenting/baby-care blog written in Brazilian Portuguese.

Topic: "{tema}"
Article title: "{titulo}"

Create exactly {num_imagens} image objects, each with:
- "prompt": the image generation prompt, IN ENGLISH.
- "legenda": a short caption for the image, IN BRAZILIAN PORTUGUESE (under 12 words),
  describing what's shown — this will be displayed under the image on the blog.

- Object 1 (COVER): eye-catching thumbnail-style image related to "{tema}". Must be warm and
  inviting: soft pastel colors, tender and calm mood, cozy nursery or home setting.{outros}

Rules for ALL prompts (MANDATORY — follow strictly):
- STYLE: soft, warm CHILDREN'S-BOOK ILLUSTRATION style (like a gentle watercolor or flat digital
  illustration). NOT photorealistic. NOT a real photograph.
- Depict babies/children only as simple, non-identifiable, generic illustrated characters —
  no realistic human faces, no photorealistic skin or anatomy.
- Fully clothed or appropriately covered in every scene (e.g. diaper-changing scenes show a
  clothed/diapered baby from a modest angle, bath scenes show a baby in a tub with water/bubbles
  covering the body). Never depict nudity or exposed genitals, even in illustrated style.
- No text, logos or words inside images.
- Warm, cozy, reassuring tone. Simple, clean, professional illustration aesthetic.
- Each "legenda" must be different from the others, specific to what that image shows.

Return ONLY a valid JSON array of {num_imagens} objects, nothing else.
Example: [{{"prompt": "...", "legenda": "..."}}, {{"prompt": "...", "legenda": "..."}}]
"""
    raw = pedir_ia_groq(prompt, temperatura=0.6)
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if match:
        try:
            itens = json.loads(match.group())
            if isinstance(itens, list):
                limpos = [
                    {
                        "prompt": str(it.get("prompt", "")).strip(),
                        "legenda": str(it.get("legenda", "")).strip() or tema,
                    }
                    for it in itens if isinstance(it, dict) and it.get("prompt")
                ]
                if limpos:
                    return limpos[:num_imagens]
        except Exception:
            pass
    # Fallback: sem legenda customizada, mas nunca quebra o fluxo
    return [{"prompt": f"{tema} gentle children's book illustration, no photorealism", "legenda": tema}
            for _ in range(num_imagens)]


# ─────────────────────────────────────────────
#  GERAÇÃO DE IMAGEM — Pollinations.ai (b64)
# ─────────────────────────────────────────────
DIMENSOES_RATIO = {
    "16:9": (1280, 720),
    "1:1": (1024, 1024),
    "9:16": (720, 1280),
}


def gerar_imagem_worker_b64(prompt_img, ratio="16:9"):
    """Gera a imagem via Pollinations.ai (gratuito, sem chave, sem cota diaria)
    e retorna o base64 bruto da imagem."""
    largura, altura = DIMENSOES_RATIO.get(ratio, (1280, 720))
    prompt_codificado = urllib.parse.quote(prompt_img)
    url = f"https://image.pollinations.ai/prompt/{prompt_codificado}"
    params = {
        "width": largura,
        "height": altura,
        "model": "flux",
        "seed": random.randint(1, 999999),
        "nologo": "true",
    }
    headers = {}
    if POLLINATIONS_TOKEN:
        headers["Authorization"] = f"Bearer {POLLINATIONS_TOKEN}"
    resp = requests.get(url, params=params, headers=headers, timeout=120)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if "image" not in content_type:
        raise ValueError(f"Resposta nao parece ser uma imagem (Content-Type: {content_type})")
    b64 = base64.b64encode(resp.content).decode("utf-8")
    if not b64:
        raise ValueError("Pollinations.ai retornou imagem vazia.")
    return b64


# ─────────────────────────────────────────────
#  HOSPEDAGEM — ImgBB (b64 → URL pública)
# ─────────────────────────────────────────────
def hospedar_imgbb(b64_data, nome="bebes_img"):
    """
    Envia o base64 para o ImgBB e retorna a URL pública da imagem.
    Levanta exceção se falhar.
    """
    if not IMGBB_API_KEY:
        raise ValueError("IMGBB_API_KEY não configurada.")

    resp = requests.post(
        "https://api.imgbb.com/1/image",
        data={
            "key":    IMGBB_API_KEY,
            "image":  b64_data,
            "name":   nome[:100],
        },
        timeout=60,
    )
    resp.raise_for_status()
    resultado = resp.json()
    if not resultado.get("success"):
        raise ValueError(f"ImgBB recusou o upload: {resultado}")
    url = resultado["data"]["url"]
    print(f"  ☁️  ImgBB hospedou: {url}")
    return url


# ─────────────────────────────────────────────
#  CONFIRMAÇÃO DE PROPAGAÇÃO DA URL
#  (evita publicar um link que ainda não está 100% acessível)
# ─────────────────────────────────────────────
def confirmar_url_acessivel(url, tentativas=4, espera=2):
    for tentativa in range(tentativas):
        try:
            r = requests.head(url, timeout=10, allow_redirects=True)
            if r.status_code == 200:
                return True
            # Alguns CDNs (ex.: ImgBB) recusam ou não respondem bem a HEAD.
            # Nesses casos, confirma com um GET leve antes de desistir.
            if r.status_code in (403, 405, 501):
                r2 = requests.get(url, timeout=10, stream=True)
                ok = r2.status_code == 200
                r2.close()
                if ok:
                    return True
        except Exception:
            pass
        time.sleep(espera)
    return False


# ─────────────────────────────────────────────
#  FALLBACK — Openverse (imagens com licença CC)
# ─────────────────────────────────────────────
def buscar_imagens_openverse(palavra_chave, quantidade=3):
    try:
        resposta = requests.get(
            "https://api.openverse.org/v1/images/",
            params={
                "q":            palavra_chave,
                "license_type": "commercial",
                "page_size":    max(quantidade, 5),
                "mature":       "false",
            },
            headers={"User-Agent": "RoboBebes/1.0"},
            timeout=15,
        )
        resultados = resposta.json().get("results", [])
        urls = [r["url"] for r in resultados[:quantidade]]
        return urls if urls else [IMAGEM_PADRAO]
    except Exception as e:
        print(f"⚠️ Erro Openverse: {e}")
        return [IMAGEM_PADRAO]


# ─────────────────────────────────────────────
#  HTML DE IMAGEM (Blogger)
# ─────────────────────────────────────────────
def html_imagem_blogger(src, legenda, height=360, width=640):
    """src deve ser sempre uma URL pública (ImgBB, Openverse ou data URI como último recurso).
    legenda vira o alt/title da imagem E o texto visível abaixo dela (padrão Blogger)."""
    return (
        '<table align="center" cellpadding="0" cellspacing="0" '
        'class="tr-caption-container" '
        'style="margin-left:auto;margin-right:auto;margin-bottom:24px;">'
        '<tbody>'
        '<tr><td style="text-align:center;">'
        f'<img alt="{legenda}" border="0" height="{height}" src="{src}" '
        f'title="{legenda}" width="{width}" '
        'style="max-width:100%;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.12);" />'
        '</td></tr>'
        '<tr><td class="tr-caption" '
        'style="text-align:center;font-size:12px;color:#888;padding-top:6px;">'
        f'{legenda}</td></tr>'
        '</tbody></table><br />'
    )


# ─────────────────────────────────────────────
#  ORQUESTRADOR DE IMAGENS
#  Cascata: Pollinations.ai → ImgBB → (fallback) Openverse
# ─────────────────────────────────────────────
def obter_imagens_html(itens_imagem, titulo, img_en_fallback):
    """
    itens_imagem: lista de dicts {"prompt": ..., "legenda": ...}

    Para cada item:
      1. Gera imagem via Pollinations.ai (b64)
      2. Hospeda no ImgBB → URL pública limpa para o Blogger
      3. Confirma (HEAD request) que a URL já está acessível antes de usar —
         evita o post cair com imagem "quebrada" até dar refresh no editor.
      4. Se Pollinations.ai falhar: tenta Openverse (URL direta, sem ImgBB)
      5. Se ImgBB falhar OU a URL não confirmar em tempo hábil: usa data URI
         base64 como último recurso (sempre carrega, não depende de CDN externo)
    """
    imagens_html    = []
    openverse_cache = None

    for i, item in enumerate(itens_imagem):
        prompt_img = item["prompt"]
        legenda    = item["legenda"]
        src = None

        # ── Tentativa 1: Pollinations.ai + ImgBB ──────────
        try:
            print(f"  🖼️  [{i+1}/{len(itens_imagem)}] Gerando via Pollinations.ai...")
            b64 = gerar_imagem_worker_b64(prompt_img, ratio="16:9")

            try:
                nome_img = f"bebes_{titulo[:40].replace(' ','_')}_{i+1}"
                src_candidata = hospedar_imgbb(b64, nome=nome_img)

                if confirmar_url_acessivel(src_candidata):
                    src = src_candidata
                    print(f"  ✅ Pollinations.ai + ImgBB OK e confirmado → {src[:60]}...")
                else:
                    print("  ⚠️  ImgBB não confirmou a tempo. Usando data URI como backup...")
                    src = f"data:image/png;base64,{b64}"
            except Exception as e_imgbb:
                # ImgBB falhou mas temos o b64 — usa data URI como backup
                print(f"  ⚠️  ImgBB falhou ({e_imgbb}). Usando data URI como backup...")
                src = f"data:image/png;base64,{b64}"

        # ── Tentativa 2: Openverse (Pollinations.ai falhou) ─
        except Exception as e_ia:
            print(f"  ⚠️  Pollinations.ai falhou ({e_ia}). Buscando no Openverse...")
            if openverse_cache is None:
                openverse_cache = buscar_imagens_openverse(
                    img_en_fallback, quantidade=len(itens_imagem)
                )
            src = openverse_cache[i % len(openverse_cache)]
            print(f"  🔄 Openverse: {src[:60]}...")

        altura = 420 if i == 0 else 300
        imagens_html.append(html_imagem_blogger(src, legenda, height=altura))

        if i < len(itens_imagem) - 1:
            time.sleep(INTERVALO_POLLINATIONS)  # respeita o rate limit do Pollinations.ai

    return imagens_html


# ─────────────────────────────────────────────
#  MONTAGEM DO HTML FINAL
# ─────────────────────────────────────────────
def montar_html(corpo_artigo, imagens_html, aviso):
    html_corpo = corpo_artigo

    # Injeta imagens de corpo nos marcadores <!--IMG_N-->
    for idx in range(1, len(imagens_html)):
        marcador = f"<!--IMG_{idx + 1}-->"
        if marcador in html_corpo:
            html_corpo = html_corpo.replace(marcador, imagens_html[idx], 1)
        else:
            # Appenda ao final se marcador não veio
            html_corpo += imagens_html[idx]

    cta = """
<div style="background-color:#fff5f7;border-left:4px solid #f48fb1;border-radius:8px;
margin:32px 0;padding:20px 24px;font-family:sans-serif;">
    <p style="font-size:16px;font-weight:bold;color:#333;margin:0 0 8px 0;">
        👶 Conta pra gente!</p>
    <p style="font-size:14px;color:#555;margin:0 0 14px 0;">
        Você já passou por essa fase com seu bebê? Deixa nos comentários sua experiência
        ou aquela dúvida que ninguém te respondeu direito — vamos conversar. 💕</p>
    <div style="display:flex;flex-wrap:wrap;gap:10px;">
        <a href="#" onclick="window.open('https://api.whatsapp.com/send?text='
+encodeURIComponent(document.title+' - '+window.location.href),'_blank');return false;"
style="background-color:#25d366;color:white;padding:9px 16px;border-radius:8px;
text-decoration:none;font-size:13px;font-weight:bold;">WhatsApp</a>
        <a href="#" onclick="window.open('https://www.facebook.com/sharer/sharer.php?u='
+encodeURIComponent(window.location.href),'_blank');return false;"
style="background-color:#1877f2;color:white;padding:9px 16px;border-radius:8px;
text-decoration:none;font-size:13px;font-weight:bold;">Facebook</a>
        <a href="#" onclick="window.open('https://twitter.com/intent/tweet?url='
+encodeURIComponent(window.location.href),'_blank');return false;"
style="background-color:#000;color:white;padding:9px 16px;border-radius:8px;
text-decoration:none;font-size:13px;font-weight:bold;">X</a>
    </div>
</div>
"""
    return f"{imagens_html[0]}{html_corpo}{cta}{aviso}"


# ─────────────────────────────────────────────
#  BLOGGER
# ─────────────────────────────────────────────
def obter_credenciais():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return creds


def publicar_no_blogger(titulo, conteudo, labels=None):
    creds   = obter_credenciais()
    blogger = build("blogger", "v3", credentials=creds)
    corpo   = {"kind": "blogger#post", "title": titulo, "content": conteudo}
    if labels:
        corpo["labels"] = labels
    res = blogger.posts().insert(blogId=BLOGGER_ID, body=corpo).execute()
    print(f"👶 Postado: '{titulo}' -> {res.get('url')}")
    print(f"🏷️  Marcadores: {', '.join(labels) if labels else '(nenhum)'}")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("👶 Gerando artigo de cuidados com bebês do dia...")

    tema        = escolher_tema()
    nome_tema   = tema["nome"]
    img_en      = tema["img_en"]

    # Número de imagens: 4 para temas de recém-nascido/primeiros cuidados, 3 para os demais
    temas_recem_nascido = {
        "Como fazer o bebê arrotar", "Primeiro banho do recém-nascido",
        "Cuidados com o coto umbilical", "Cuidados com bebês prematuros",
        "Teste do pezinho e exames do bebê", "Enxoval essencial para recém-nascido",
    }
    num_imagens = 4 if nome_tema in temas_recem_nascido else 3

    print(f"📝 Gerando título...")
    titulo = gerar_titulo(nome_tema)
    print(f"✏️  Título: {titulo}")

    print(f"🏷️  Gerando marcadores...")
    tags = gerar_tags(nome_tema, titulo)
    print(f"🏷️  Marcadores: {tags}")

    print(f"🖊️  Gerando prompts e legendas de imagem...")
    itens_imagem = gerar_prompts_imagens(nome_tema, titulo, num_imagens)

    print(f"🖼️  Obtendo {num_imagens} imagens...")
    imagens_html = obter_imagens_html(itens_imagem, titulo, img_en)

    print(f"📖 Escrevendo artigo sobre {nome_tema}...")
    corpo = gerar_artigo_cuidados(nome_tema, num_imagens)

    aviso = (
        '<p style="font-size:12px;color:#999;font-style:italic;margin-top:24px;">'
        '👩‍⚕️ Este conteúdo é informativo e não substitui a avaliação de um médico pediatra. '
        'Em caso de dúvidas, sintomas ou qualquer situação de saúde do seu bebê, procure sempre '
        'um profissional de saúde.</p>'
    )

    html_final = montar_html(corpo, imagens_html, aviso)
    publicar_no_blogger(titulo, html_final, labels=tags)
    marcar_tema_usado(nome_tema)
    print(f"✅ Concluído! Tema postado: {nome_tema}")
