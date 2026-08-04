#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GÉNÉRATEUR DE CARTES D'ACCÈS — JDR ALIEN
=========================================
Cartes recto/verso au format 88 x 63 mm (paysage, taille "carte de jeu"), 300 DPI,
aux couleurs des grandes compagnies (palettes tirées des logos officiels) :
  - Weyland-Yutani        (noir / jaune signal / gris)
  - Seegson               (noir chaud / or / olive, rétro 70s)
  - Prodigy Corporation   (papier clair / noir, monochrome)
  - Lasalle Bionational   (nuit / bleu acier / gris)

Usage :
    python3 generateur_cartes.py [personnages.json]

Sorties (dossier ./cartes/) :
    - NOM_Prenom_recto.png / _verso.png   (300 DPI, coins arrondis)
    - planche_impression.pdf              (A4, 8 cartes/page, versos en miroir)
    - apercu.png                          (montage de toutes les cartes)

LOGOS : chaque personnage peut définir "logo_grand" et "logo_petit" (chemins
d'images : png/webp/jpg). Le fond uni du logo (noir, blanc...) est détouré
automatiquement. À défaut : ./logos/<compagnie>.(png|webp|jpg), sinon un logo
stylisé est dessiné en code.

TEXTES : tous les libellés des cartes sont surchargeables, soit par compagnie
(clé "textes_compagnies" à la racine du JSON), soit par personnage (clé
"textes"). Voir THEMES[...]["textes"] pour la liste des clés. Les valeurs
peuvent contenir {n} (niveau d'habilitation), {id}, {site}, {division}, {gs},
{annee}.

DONNÉES : les valeurs générées (id, habilitation, division, site,
groupe_sanguin, emis, exp, serie) peuvent être fixées directement dans le
personnage, p. ex. "habilitation": 5.
"""

import json
import math
import os
import random
import sys
import unicodedata

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# ---------------------------------------------------------------------------
# CONFIGURATION GÉNÉRALE
# ---------------------------------------------------------------------------
DPI = 300
CARD_W_MM, CARD_H_MM = 88.0, 63.0          # format "carte de jeu" (paysage)
ANNEE_DEFAUT = 2183

def mm2px(mm: float) -> int:
    return round(mm / 25.4 * DPI)

W, H = mm2px(CARD_W_MM), mm2px(CARD_H_MM)  # 1039 x 744 px
RADIUS = mm2px(3.0)
MARGE = 44

DOSSIER_SORTIE = "cartes"
DOSSIER_LOGOS = "logos"

# ---------------------------------------------------------------------------
# POLICES
# ---------------------------------------------------------------------------
_CHEMINS_POLICES = {
    "corpo":    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "corpo_b":  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "retro":    "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf",
    "retro_m":  "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
    "retro_b":  "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "retro_l":  "/usr/share/fonts/truetype/google-fonts/Poppins-Light.ttf",
    "mono":     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "mono_b":   "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "cond":     "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "cond_b":   "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "ital":     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    "sans":     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "sans_b":   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}
_CACHE_POLICES = {}

def F(nom: str, taille: int) -> ImageFont.FreeTypeFont:
    """Charge une police avec cache. Repli sur DejaVu Sans si absente."""
    cle = (nom, taille)
    if cle not in _CACHE_POLICES:
        chemin = _CHEMINS_POLICES.get(nom, _CHEMINS_POLICES["sans"])
        if not os.path.exists(chemin):
            chemin = _CHEMINS_POLICES["sans"]
        _CACHE_POLICES[cle] = ImageFont.truetype(chemin, taille)
    return _CACHE_POLICES[cle]

# ---------------------------------------------------------------------------
# HELPERS DE DESSIN
# ---------------------------------------------------------------------------
def nouvelle_face(couleur) -> Image.Image:
    return Image.new("RGBA", (W, H), couleur)

def arrondir_coins(img: Image.Image) -> Image.Image:
    masque = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(masque)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=RADIUS, fill=255)
    sortie = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sortie.paste(img, (0, 0), masque)
    return sortie

def largeur_texte(texte: str, police) -> int:
    b = police.getbbox(texte)
    return b[2] - b[0]

def texte_espace(draw, xy, texte, police, fill, tracking=0, ancre="l"):
    """Texte avec interlettrage (tracking en px). ancre: l/m/r, y = haut."""
    largeurs = [largeur_texte(c, police) for c in texte]
    total = sum(largeurs) + tracking * max(0, len(texte) - 1)
    x, y = xy
    if ancre == "m":
        x -= total // 2
    elif ancre == "r":
        x -= total
    for c, lw in zip(texte, largeurs):
        draw.text((x, y), c, font=police, fill=fill)
        x += lw + tracking
    return total

def texte_ajuste(draw, xy, texte, nom_police, taille_max, largeur_max, fill,
                 taille_min=16, ancre="la"):
    """Dessine un texte en réduisant la taille pour tenir dans largeur_max."""
    taille = taille_max
    while taille > taille_min:
        p = F(nom_police, taille)
        if largeur_texte(texte, p) <= largeur_max:
            break
        taille -= 2
    draw.text(xy, texte, font=F(nom_police, taille), fill=fill, anchor=ancre)
    return taille

def calque(dessin_fn, blur=0):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    dessin_fn(d, img)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return img

def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")

# ---------------------------------------------------------------------------
# COMPOSANTS GRAPHIQUES
# ---------------------------------------------------------------------------
def code_barres(draw, x, y, w, h, rng, fill):
    cx = x
    while cx < x + w - 8:
        bw = rng.choice([3, 3, 4, 6, 6, 9, 12])
        if rng.random() > 0.42:
            draw.rectangle([cx, y, cx + bw, y + h], fill=fill)
        cx += bw + rng.choice([3, 4, 5])

def bande_magnetique(img, y0, y1, base=(12, 12, 14, 255), reflet=(70, 70, 78, 255)):
    d = ImageDraw.Draw(img)
    d.rectangle([0, y0, W, y1], fill=base)
    for i in range(3):
        yy = y0 + (y1 - y0) * (0.25 + i * 0.22)
        d.line([(0, yy), (W, yy)], fill=reflet, width=2)

def micro_texte(draw, x, y, w, texte, fill, taille=11):
    p = F("mono", taille)
    motif = (texte + " • ")
    rep = motif * (w // max(1, largeur_texte(motif, p)) + 2)
    # tronque proprement à la largeur demandée
    while rep and largeur_texte(rep, p) > w:
        rep = rep[:-1]
    draw.text((x, y), rep, font=p, fill=fill)

def ligne_mrz(perso, prefixe, longueur=44):
    nom = sans_accents(perso["nom"]).upper().replace(" ", "<")
    pre = sans_accents(perso["prenom"]).upper().replace(" ", "<")
    brut = f"{prefixe}<ACC<{nom}<<{pre}"
    brut = (brut + "<" * longueur)[:longueur - 5]
    return brut + perso["_id_court"]

def ligne_mrz2(perso, annee, longueur=44):
    ident = sans_accents(perso["_id"]).upper()
    for ch in "-/ .":
        ident = ident.replace(ch, "<")
    brut = f"{ident}<{annee}<{perso['_sang'].replace('+','P').replace('-','M')}"
    brut = (brut + "<" * longueur)[:longueur - 5]
    return brut + perso["_serie"].replace("-", "")[:5]

def pastilles_habilitation(draw, x, y, niveau, actif, inactif, taille=26, ecart=12,
                           forme="carre", total=5):
    for i in range(total):
        cx = x + i * (taille + ecart)
        c = actif if i < niveau else inactif
        if forme == "carre":
            draw.rectangle([cx, y, cx + taille, y + taille], fill=c)
        elif forme == "rond":
            draw.ellipse([cx, y, cx + taille, y + taille], fill=c)
        elif forme == "barre":
            draw.rounded_rectangle([cx, y, cx + taille, y + taille // 2], radius=6, fill=c)
        elif forme == "hex":
            r = taille / 2
            pts = [(cx + r + r * math.cos(math.radians(a)),
                    y + r + r * math.sin(math.radians(a))) for a in range(0, 360, 60)]
            draw.polygon(pts, fill=c)

def rayures_diagonales_coin(img, coin, couleurs, largeur=42, ecart=22):
    """Bandes diagonales traversant un coin. coin: 'tr', 'tl', 'br', 'bl'."""
    d = ImageDraw.Draw(img)
    L = 700
    for i, c in enumerate(couleurs):
        off = i * (largeur + ecart)
        if coin == "tr":
            base = W - 300 + off
            d.polygon([(base, 0), (base - L, L), (base - L - largeur, L),
                       (base - largeur, 0)], fill=c)
        elif coin == "tl":
            base = 300 - off
            d.polygon([(base, 0), (base - L, L), (base - L - largeur, L),
                       (base - largeur, 0)], fill=c)
        elif coin == "br":
            base = W - 300 + off
            d.polygon([(base, H), (base + L, H - L), (base + L + largeur, H - L),
                       (base + largeur, H)], fill=c)
        else:  # 'bl'
            base = 300 - off
            d.polygon([(base, H), (base - L, H - L), (base - L - largeur, H - L),
                       (base - largeur, H)], fill=c)

def chevrons_danger(img, y0, y1, c1, c2, pas=44):
    d = ImageDraw.Draw(img)
    d.rectangle([0, y0, W, y1], fill=c1)
    hh = y1 - y0
    x = -hh
    while x < W + hh:
        d.polygon([(x, y1), (x + hh, y0), (x + hh + pas // 2, y0),
                   (x + pas // 2, y1)], fill=c2)
        x += pas
    return d

def double_helice(img, cx, y0, y1, amplitude, couleur, alpha=70, periodes=2.2, ep=6, rungs=9):
    c = couleur[:3] + (alpha,)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    pts1, pts2 = [], []
    hauteur = y1 - y0
    for t in range(0, 101):
        y = y0 + hauteur * t / 100
        ph = 2 * math.pi * periodes * t / 100
        pts1.append((cx + amplitude * math.sin(ph), y))
        pts2.append((cx + amplitude * math.sin(ph + math.pi), y))
    d.line(pts1, fill=c, width=ep, joint="curve")
    d.line(pts2, fill=c, width=ep, joint="curve")
    for k in range(rungs):
        t = (k + 0.5) / rungs
        y = y0 + hauteur * t
        ph = 2 * math.pi * periodes * t
        x1 = cx + amplitude * math.sin(ph)
        x2 = cx + amplitude * math.sin(ph + math.pi)
        d.line([(x1, y), (x2, y)], fill=c, width=max(3, ep - 2))
    img.alpha_composite(lay)

def maillage_hexagonal(img, x0, y0, x1, y1, couleur, alpha=26, taille=52):
    c = couleur[:3] + (alpha,)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    dx = taille * 1.5
    dy = taille * math.sqrt(3) / 2
    lig = 0
    y = y0
    while y < y1 + taille:
        x = x0 + (dx / 2 if lig % 2 else 0)
        while x < x1 + taille:
            pts = [(x + taille * math.cos(math.radians(a)),
                    y + taille * math.sin(math.radians(a))) for a in range(0, 360, 60)]
            d.polygon(pts, outline=c, width=2)
            x += dx
        y += dy
        lig += 1
    img.alpha_composite(lay)

def grille_fine(img, x0, y0, x1, y1, couleur, alpha=255, pas=76):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    c = couleur[:3] + (alpha,)
    x = x0
    while x <= x1:
        d.line([(x, y0), (x, y1)], fill=c, width=1)
        x += pas
    y = y0
    while y <= y1:
        d.line([(x0, y), (x1, y)], fill=c, width=1)
        y += pas
    img.alpha_composite(lay)

def crochets_reticule(draw, x0, y0, x1, y1, lg=34, ep=6, fill=(255, 255, 255)):
    for (cx, cy, sx, sy) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        draw.line([(cx, cy), (cx + sx * lg, cy)], fill=fill, width=ep)
        draw.line([(cx, cy), (cx, cy + sy * lg)], fill=fill, width=ep)

def fente_badge(draw, cx, y, w=110, h=22, contour=(0, 0, 0), fond=(255, 255, 255)):
    draw.rounded_rectangle([cx - w // 2, y, cx + w // 2, y + h], radius=h // 2,
                           fill=fond, outline=contour, width=4)

# ---------------------------------------------------------------------------
# PHOTO : optionnelle — sans chemin, le cadre n'est pas dessiné
# ---------------------------------------------------------------------------
def preparer_photo(chemin, w, h, sombre, clair):
    try:
        img = Image.open(chemin).convert("L")
    except Exception:
        return None
    img = ImageOps.fit(img, (w, h), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=2)
    return ImageOps.colorize(img, black=sombre[:3], white=clair[:3]).convert("RGBA")

def silhouette(w, h, fond, forme_c, texte_c=None):
    img = Image.new("RGBA", (w, h), fond)
    d = ImageDraw.Draw(img)
    cx = w / 2
    r_tete = w * 0.21
    cy_tete = h * 0.36
    d.ellipse([cx - r_tete, cy_tete - r_tete, cx + r_tete, cy_tete + r_tete], fill=forme_c)
    d.pieslice([cx - w * 0.36, h * 0.60, cx + w * 0.36, h * 1.35], 180, 360, fill=forme_c)
    if texte_c:
        d.text((cx, h - 26), "PHOTO", font=F("mono", 20), fill=texte_c, anchor="mm")
    return img

def photo_ou_silhouette(perso, t, w, h):
    photo = None
    if perso.get("photo"):
        photo = preparer_photo(perso["photo"], w, h, t["photo_sombre"], t["photo_claire"])
    if photo is None:
        photo = silhouette(w, h, t["silh_fond"], t["silh_forme"], t.get("silh_texte"))
    return photo

# ---------------------------------------------------------------------------
# LOGOS — images fournies par l'utilisateur (fond détouré automatiquement)
#         ou logos stylisés dessinés en code (repli)
# ---------------------------------------------------------------------------
_CACHE_LOGOS = {}

def _detourer_fond(img):
    """Rend transparent le fond uni (couleur médiane des 4 coins), avec un
    dégradé sur les bords pour un détourage doux."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    coins = [px[2, 2], px[w - 3, 2], px[2, h - 3], px[w - 3, h - 3]]
    bg = tuple(sorted(c[i] for c in coins)[1] for i in range(3))
    t1, t2 = 55, 105          # seuils de distance couleur (détouré / conservé)
    t1c, t2c = t1 * t1, t2 * t2
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            d2 = (r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2
            if d2 <= t1c:
                px[x, y] = (r, g, b, 0)
            elif d2 < t2c:
                f = (math.sqrt(d2) - t1) / (t2 - t1)
                px[x, y] = (r, g, b, int(a * f))
    return img

def charger_logo_fichier(chemin, w_max, h_max):
    cle = (chemin, w_max, h_max)
    if cle in _CACHE_LOGOS:
        return _CACHE_LOGOS[cle]
    try:
        img = Image.open(chemin).convert("RGBA")
    except Exception as e:
        print(f"  [!] logo introuvable : {chemin} ({e})")
        return None
    img.thumbnail((w_max, h_max), Image.LANCZOS)
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] > 250:          # pas de transparence -> on détoure
        img = _detourer_fond(img)
    _CACHE_LOGOS[cle] = img
    return img

def logo_wy_code(s, couleur):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = s / 2
    n, ep, ecart_v = 4, s * 0.085, s * 0.055
    y_base, gap, lg_max, pente = s * 0.80, s * 0.075, s * 0.42, s * 0.10
    for i in range(n):
        y1 = y_base - i * (ep + ecart_v)
        y0 = y1 - ep
        lg = lg_max * (1 - i * 0.16)
        d.polygon([(cx + gap, y0), (cx + gap + lg, y0 - pente),
                   (cx + gap + lg, y0 - pente + ep), (cx + gap, y1)], fill=couleur)
        d.polygon([(cx - gap, y0), (cx - gap - lg, y0 - pente),
                   (cx - gap - lg, y0 - pente + ep), (cx - gap, y1)], fill=couleur)
    hc, wc, yc = s * 0.70, s * 0.10, s * 0.10
    d.polygon([(cx, yc), (cx + wc, yc + hc * 0.42), (cx, yc + hc),
               (cx - wc, yc + hc * 0.42)], fill=couleur)
    return img

def logo_seegson_code(s, couleur, secondaire=None):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    sec = secondaire or couleur
    m = s * 0.06
    d.ellipse([m, m, s - m, s - m], outline=couleur, width=max(4, int(s * 0.07)))
    d.text((s / 2, s / 2 - s * 0.02), "S", font=F("retro_b", int(s * 0.62)),
           fill=sec, anchor="mm")
    return img

def logo_prodigy_code(s, couleur, secondaire=None):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = s * 0.10
    p1, p2, p3 = (s / 2, m), (m, s - m), (s - m, s - m)
    d.line([p1, p2, p3, p1], fill=couleur, width=max(4, int(s * 0.05)), joint="curve")
    d.text((s / 2, s * 0.62), "P", font=F("retro_m", int(s * 0.40)),
           fill=couleur, anchor="mm")
    return img

def logo_lasalle_code(s, couleur, secondaire=None):
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    sec = secondaire or couleur
    ep = max(5, int(s * 0.06))
    m = s * 0.05
    d.ellipse([m, m, s - m, s - m], outline=couleur, width=ep)
    amp, y0, y1 = s * 0.16, s * 0.22, s * 0.78
    pts1, pts2 = [], []
    for t in range(0, 101):
        y = y0 + (y1 - y0) * t / 100
        ph = 2 * math.pi * 1.5 * t / 100
        pts1.append((s / 2 + amp * math.sin(ph), y))
        pts2.append((s / 2 + amp * math.sin(ph + math.pi), y))
    d.line(pts1, fill=couleur, width=max(4, int(s * 0.045)), joint="curve")
    d.line(pts2, fill=sec, width=max(4, int(s * 0.045)), joint="curve")
    for k in range(5):
        t = (k + 0.5) / 5
        y = y0 + (y1 - y0) * t
        ph = 2 * math.pi * 1.5 * t
        d.line([(s / 2 + amp * math.sin(ph), y),
                (s / 2 + amp * math.sin(ph + math.pi), y)],
               fill=couleur, width=max(3, int(s * 0.03)))
    return img

_LOGOS_CODE = {"wy": logo_wy_code, "seegson": logo_seegson_code,
               "prodigy": logo_prodigy_code, "lasalle": logo_lasalle_code}

def obtenir_logo(perso, cle, quel, w_max, h_max, t):
    """quel: 'grand' ou 'petit'. Priorité :
    1. chemin défini dans le personnage ("logo_grand"/"logo_petit")
    2. fichier ./logos/<cle>.(png|webp|jpg|jpeg)
    3. logo stylisé dessiné en code."""
    chemin = perso.get(f"logo_{quel}")
    if chemin:
        img = charger_logo_fichier(chemin, w_max, h_max)
        if img is not None:
            return img
    for ext in ("png", "webp", "jpg", "jpeg"):
        c = os.path.join(DOSSIER_LOGOS, f"{cle}.{ext}")
        if os.path.exists(c):
            img = charger_logo_fichier(c, w_max, h_max)
            if img is not None:
                return img
    fn = _LOGOS_CODE[cle]
    s = min(w_max, h_max)
    if cle == "wy":
        return fn(s, t["accent"])
    return fn(s, t["accent"], t.get("accent2", t["accent"]))

def poser_logo_centre(img, logo, cx, cy):
    """Colle le logo centré sur (cx, cy). Retourne (x0, y0, x1, y1) occupés."""
    x0 = int(cx - logo.width / 2)
    y0 = int(cy - logo.height / 2)
    img.alpha_composite(logo, (x0, y0))
    return x0, y0, x0 + logo.width, y0 + logo.height

# ---------------------------------------------------------------------------
# DONNÉES GÉNÉRÉES (déterministes) + SURCHARGES UTILISATEUR
# ---------------------------------------------------------------------------
NORMALISATION = {
    "weyland-yutani": "wy", "weyland yutani": "wy", "weyland": "wy", "wy": "wy",
    "seegson": "seegson",
    "prodigy": "prodigy", "prodigy corporation": "prodigy", "prodigy corp": "prodigy",
    "lasalle": "lasalle", "lasalle bionational": "lasalle",
    "lasalle-bionational": "lasalle", "bionational": "lasalle",
}

DONNEES_COMPAGNIES = {
    "wy": {
        "id_fmt": "WY-{a}{n:06d}",
        "secteurs": ["EXPLOITATION EXTRASOLAIRE", "DIVISION TERRAFORMATION",
                     "TRANSPORT COMMERCIAL", "PROJETS SPÉCIAUX", "BIO-DIVISION",
                     "ADMINISTRATION COLONIALE"],
        "sites": ["GATEWAY STATION", "LV-426 / HADLEY'S HOPE", "SOL — TERRE HQ",
                  "USCSS MONTERO", "ANCHORPOINT", "TITAN OUTPOST"],
    },
    "seegson": {
        "id_fmt": "SG/{a}-{n4:04d}",
        "secteurs": ["SYNTHÉTIQUES SÉRIE WJ", "COMMUNICATIONS", "MAINTENANCE ORBITALE",
                     "SYSTÈMES APOLLO", "LOGISTIQUE FRONTIÈRE", "ÉLECTROMÉNAGER SPATIAL"],
        "sites": ["STATION SEVASTOPOL", "LORENZ SYSTECH SPIRE", "KG-348",
                  "LUNA ANNEXE B", "SOLOMONS HABITATION"],
    },
    "prodigy": {
        "id_fmt": "PRD-{n4:04d}-{x}",
        "secteurs": ["RECHERCHE NEURO-SYNTHÉTIQUE", "HYBRIDES & PROTOTYPES",
                     "CYBERNÉTIQUE AVANCÉE", "ACQUISITIONS", "SÉCURITÉ INTERNE",
                     "PROGRAMME WONDERLAND"],
        "sites": ["ÎLE DE NEVERLAND", "NEW SIAM HQ", "LAB ORBITAL 7",
                  "CAMPUS PACIFIQUE", "SITE PETER-01"],
    },
    "lasalle": {
        "id_fmt": "LB-{x}{n4:04d}",
        "secteurs": ["XÉNOBIOLOGIE", "PHARMACOLOGIE APPLIQUÉE", "GÉNIE GÉNÉTIQUE",
                     "CONFINEMENT NIVEAU 4", "PROSPECTION BIOLOGIQUE", "VIROLOGIE"],
        "sites": ["COMPLEXE LISBONNE", "RODINA STATION", "LABO GUYANE-3",
                  "PLATEFORME CHARON", "SITE ELIZA"],
    },
}

GROUPES_SANGUINS = ["O+", "O+", "O-", "A+", "A+", "A-", "B+", "B-", "AB+", "AB-"]

# clé JSON utilisateur -> clé interne
SURCHARGES_DONNEES = {
    "id": "_id", "habilitation": "_habilitation", "division": "_secteur",
    "secteur": "_secteur", "site": "_site", "groupe_sanguin": "_sang",
    "emis": "_emission", "exp": "_expiration", "serie": "_serie",
}

def generer_donnees(perso, cle, annee):
    rng = random.Random(f"{cle}|{perso['nom']}|{perso['prenom']}")
    dc = DONNEES_COMPAGNIES[cle]
    n = rng.randint(0, 999999)
    x = "".join(rng.choices("ACDEFHKLMNPRTUVWX", k=2))
    perso["_rng"] = rng
    perso["_id"] = dc["id_fmt"].format(a=str(annee)[-2:], n=n % 1000000,
                                       n4=n % 10000, x=x)
    perso["_habilitation"] = rng.randint(1, 5)
    perso["_secteur"] = rng.choice(dc["secteurs"])
    perso["_site"] = rng.choice(dc["sites"])
    perso["_sang"] = rng.choice(GROUPES_SANGUINS)
    jm = (rng.randint(1, 28), rng.randint(1, 12))
    duree = rng.choice([2, 3, 3, 5])
    perso["_emission"] = f"{jm[0]:02d}.{jm[1]:02d}.{annee}"
    perso["_expiration"] = f"{jm[0]:02d}.{jm[1]:02d}.{annee + duree}"
    perso["_serie"] = "".join(rng.choices("0123456789ABCDEF", k=12))
    perso["_serie"] = "-".join([perso["_serie"][i:i+4] for i in (0, 4, 8)])
    # surcharges utilisateur
    for cle_json, cle_int in SURCHARGES_DONNEES.items():
        if cle_json in perso and perso[cle_json] not in (None, ""):
            perso[cle_int] = perso[cle_json]
    try:
        perso["_habilitation"] = max(0, min(5, int(perso["_habilitation"])))
    except (TypeError, ValueError):
        perso["_habilitation"] = 3
    chiffres = "".join(c for c in str(perso["_id"]) if c.isalnum())
    perso["_id_court"] = (chiffres[-5:] or "00000").rjust(5, "0")
    return perso

# ---------------------------------------------------------------------------
# THÈMES — palettes tirées des logos officiels + tous les textes des cartes
# ---------------------------------------------------------------------------
THEMES = {
    "wy": {
        "fond": (11, 11, 11, 255),
        "accent": (252, 252, 12, 255),      # jaune signal du logo
        "gris": (176, 176, 176, 255),
        "gris_f": (120, 120, 120, 255),
        "blanc": (240, 240, 238, 255),
        "grille": (30, 30, 30, 255),
        "photo_sombre": (14, 14, 10, 255), "photo_claire": (216, 214, 196, 255),
        "silh_fond": (26, 26, 24, 255), "silh_forme": (74, 74, 66, 255),
        "silh_texte": (120, 120, 112, 255),
        "textes": {
            "raison": "WEYLAND-YUTANI CORP",
            "entete": "CARTE D'ACCÈS",
            "sous_entete": "PERSONNEL AUTORISÉ",
            "l_nom": "NOM / SURNAME", "l_prenom": "PRÉNOM / FIRST NAME",
            "l_fonction": "FONCTION / POSITION", "l_identifiant": "IDENTIFIANT RÉSEAU",
            "l_habilitation": "HABILITATION", "l_id": "ID EMPLOYÉ",
            "l_division": "DIV.", "l_site": "SITE",
            "l_emis": "ÉMIS", "l_exp": "EXP", "l_serie": "S/N",
            "code_titre": "CODE D'ACCÈS PERSONNEL — CONFIDENTIEL",
            "propriete": "PROPRIÉTÉ DE WEYLAND-YUTANI CORP.",
            "micro": "WEYLAND-YUTANI — BUILDING BETTER WORLDS",
            "mrz_prefixe": "WY",
        },
    },
    "seegson": {
        "fond": (20, 16, 10, 255),
        "accent": (156, 132, 60, 255),      # or du logo
        "accent2": (180, 180, 108, 255),    # olive clair du logo
        "gris": (176, 176, 176, 255),
        "clair": (232, 226, 202, 255),
        "inactif": (58, 50, 36, 255),
        "photo_sombre": (24, 19, 10, 255), "photo_claire": (214, 204, 158, 255),
        "silh_fond": (33, 27, 16, 255), "silh_forme": (104, 88, 48, 255),
        "silh_texte": (150, 130, 80, 255),
        "textes": {
            "raison": "SEEGSON",
            "entete": "CARTE PERSONNEL",
            "sous_entete": "TOMORROW, TOGETHER ™",
            "l_nom": "NOM", "l_prenom": "PRÉNOM",
            "l_fonction": "FONCTION", "l_identifiant": "IDENTIFIANT",
            "l_habilitation": "HABILITATION", "l_id": "N°",
            "l_division": "DIV.", "l_site": "SITE",
            "l_emis": "ÉMIS", "l_exp": "EXP", "l_serie": "S/N",
            "bandeau": "TOMORROW, TOGETHER ™",
            "code_titre": "CODE TERMINAL — SYSTÈME APOLLO",
            "propriete": "PROPRIÉTÉ DE SEEGSON CORP. — RETOUR EXIGÉ",
            "micro": "SEEGSON SYNTHETICS — SYSTÈME APOLLO",
        },
    },
    "prodigy": {
        "fond": (236, 234, 229, 255),       # papier clair du logo
        "noir": (18, 18, 18, 255),
        "gris": (106, 104, 100, 255),
        "regle": (198, 196, 190, 255),
        "blanc": (250, 250, 248, 255),
        "photo_sombre": (22, 22, 22, 255), "photo_claire": (236, 234, 229, 255),
        "silh_fond": (222, 220, 214, 255), "silh_forme": (60, 60, 58, 255),
        "silh_texte": (150, 148, 142, 255),
        "textes": {
            "raison": "PRODIGY CORPORATION",
            "entete": "PRODIGY CORP",
            "sous_entete": "ACCESS // ID",
            "l_nom": "NOM", "l_prenom": "PRÉNOM",
            "l_fonction": "FONCTION", "l_identifiant": "IDENTIFIANT",
            "l_habilitation": "NIVEAU D'ACCÈS", "l_id": "ID",
            "l_division": "DIV.", "l_site": "SITE",
            "l_emis": "ÉMIS", "l_exp": "EXP", "l_serie": "S/N",
            "code_titre": "CLÉ D'ACCÈS NEURO-LINK — NE PAS DIVULGUER",
            "pied": "{division} — {site}",
            "propriete": "USAGE INTERNE — PROPRIÉTÉ DE PRODIGY CORP",
            "micro": "PRODIGY CORP — WONDERLAND",
        },
    },
    "lasalle": {
        "fond": (9, 16, 23, 255),
        "accent": (60, 132, 156, 255),      # bleu acier du logo
        "accent2": (150, 196, 214, 255),    # bleu clair
        "gris": (176, 176, 176, 255),
        "clair": (226, 234, 238, 255),
        "sombre": (4, 8, 12, 255),
        "photo_sombre": (6, 12, 18, 255), "photo_claire": (188, 214, 226, 255),
        "silh_fond": (16, 26, 34, 255), "silh_forme": (52, 92, 110, 255),
        "silh_texte": (110, 150, 168, 255),
        "textes": {
            "raison": "LASALLE BIONATIONAL",
            "entete": "ACCÈS CONTRÔLÉ",
            "sous_entete": "DIVISION BIOSCIENCES",
            "l_nom": "NOM", "l_prenom": "PRÉNOM",
            "l_fonction": "FONCTION", "l_identifiant": "IDENTIFIANT",
            "l_habilitation": "BIO-CONFINEMENT — NIVEAU {n}",
            "l_id": "ID EMPLOYÉ", "l_division": "DIV.", "l_site": "SITE",
            "l_gs": "GS", "l_emis": "ÉMIS", "l_exp": "EXP", "l_serie": "S/N",
            "code_titre": "SÉQUENCE D'ACCÈS LABORATOIRE",
            "propriete": "ÉCHANTILLONS BIOLOGIQUES — MANIPULATION RESTREINTE",
            "micro": "LASALLE BIONATIONAL — CONFINEMENT",
        },
    },
}

def T(perso, t, cle_txt, defaut=""):
    """Texte du thème avec placeholders {n} {id} {site} {division} {gs} {annee}."""
    s = t["textes"].get(cle_txt, defaut)
    return (s.replace("{n}", str(perso.get("_habilitation", "")))
             .replace("{id}", str(perso.get("_id", "")))
             .replace("{site}", str(perso.get("_site", "")))
             .replace("{division}", str(perso.get("_secteur", "")))
             .replace("{gs}", str(perso.get("_sang", "")))
             .replace("{annee}", str(perso.get("_annee", ""))))

def champ(draw, x, y, label, valeur, c_label, c_valeur, p_label, p_valeur,
          largeur_max, tracking_label=3):
    texte_espace(draw, (x, y), label, p_label, c_label, tracking=tracking_label)
    texte_ajuste(draw, (x, y + p_label.size + 8), valeur, p_valeur[0], p_valeur[1],
                 largeur_max, c_valeur)

# ---------------------------------------------------------------------------
# THÈME 1 : WEYLAND-YUTANI — noir / jaune signal / gris
# ---------------------------------------------------------------------------
def wy_recto(perso, t):
    img = nouvelle_face(t["fond"])
    grille_fine(img, 0, 0, W, H, t["grille"], alpha=255, pas=74)
    d = ImageDraw.Draw(img)

    # Logo petit en tête, à gauche
    logo = obtenir_logo(perso, "wy", "petit", 330, 168, t)
    img.alpha_composite(logo, (MARGE, 28))
    d = ImageDraw.Draw(img)
    texte_espace(d, (W - MARGE, 44), T(perso, t, "entete"), F("corpo_b", 26),
                 t["blanc"], tracking=3, ancre="r")
    texte_espace(d, (W - MARGE, 88), T(perso, t, "sous_entete"), F("corpo", 15),
                 t["gris_f"], tracking=3, ancre="r")
    d.rectangle([MARGE, 212, W - MARGE, 216], fill=t["accent"])

    # Photo à droite (optionnelle)
    pw, ph = 240, 300
    px0, py0 = W - MARGE - pw, 240
    if perso.get("photo"):
        img.paste(photo_ou_silhouette(perso, t, pw, ph), (px0, py0))
        d.rectangle([px0 - 4, py0 - 4, px0 + pw + 4, py0 + ph + 4],
                    outline=t["accent"], width=4)

    # Habilitation
    texte_espace(d, (px0 - 70, py0 + ph + 22), T(perso, t, "l_habilitation"),
                 F("corpo", 14), t["gris_f"], tracking=2)
    pastilles_habilitation(d, px0 + pw - (5 * 20 + 4 * 8), py0 + ph + 16,
                           perso["_habilitation"], t["accent"], (48, 48, 44, 255),
                           taille=20, ecart=8)

    # Champs identité à gauche
    cl, cv = t["gris_f"], t["blanc"]
    pl = F("corpo", 15)
    x = MARGE
    lg = (px0 - MARGE - 30) if perso.get("photo") else (W - 2 * MARGE)
    champ(d, x, 240, T(perso, t, "l_nom"), perso["nom"].upper(), cl, cv, pl, ("corpo_b", 38), lg)
    champ(d, x, 314, T(perso, t, "l_prenom"), perso["prenom"], cl, cv, pl, ("corpo_b", 34), lg)
    champ(d, x, 388, T(perso, t, "l_fonction"), perso["profession"], cl, cv, pl, ("corpo_b", 29), lg)
    champ(d, x, 462, T(perso, t, "l_identifiant"), perso["username"], cl, t["accent"], pl, ("mono_b", 27), lg)

    # Pied : ID + code-barres + division/site/dates
    d.rectangle([MARGE, 596, W - MARGE, 598], fill=t["accent"])
    texte_espace(d, (MARGE, 610), T(perso, t, "l_id"), F("corpo", 14), cl, tracking=3)
    d.text((MARGE, 632), str(perso["_id"]), font=F("mono_b", 38), fill=t["blanc"])
    code_barres(d, 434, 616, 246, 56, perso["_rng"], t["gris"])
    for i, ligne in enumerate([
            f"{T(perso, t, 'l_division')} {perso['_secteur']}",
            f"{T(perso, t, 'l_site')} {perso['_site']}",
            f"{T(perso, t, 'l_emis')} {perso['_emission']}",
            f"{T(perso, t, 'l_exp')}  {perso['_expiration']}"]):
        texte_ajuste(d, (W - MARGE, 600 + i * 24), ligne, "mono", 14,
                     318, t["gris"], ancre="ra")
    chevrons_danger(img, H - 52, H - 16, (16, 16, 14, 255), t["accent"])
    return arrondir_coins(img)

def wy_verso(perso, t):
    img = nouvelle_face(t["fond"])
    bande_magnetique(img, 54, 150, base=(28, 28, 28, 255), reflet=(52, 52, 52, 255))
    d = ImageDraw.Draw(img)

    logo = obtenir_logo(perso, "wy", "grand", 520, 278, t)
    poser_logo_centre(img, logo, W // 2, 300)
    d = ImageDraw.Draw(img)

    flavor = perso.get("flavor") or T(perso, t, "micro")
    texte_ajuste(d, (W // 2, 462), f"« {flavor} »", "ital", 23, W - 2 * MARGE - 60,
                 (206, 206, 200, 255), ancre="ma")

    # Boîte code : fond jaune, texte noir
    bx0, bx1, by0, by1 = 230, W - 230, 552, 618
    texte_espace(d, (W // 2, 520), T(perso, t, "code_titre"), F("corpo", 15),
                 t["gris"], tracking=2, ancre="m")
    d.rectangle([bx0, by0, bx1, by1], fill=t["accent"])
    texte_ajuste(d, ((bx0 + bx1) // 2, (by0 + by1) // 2 + 2), str(perso["password"]),
                 "mono_b", 40, bx1 - bx0 - 44, (12, 12, 10, 255), ancre="mm")

    d.text((MARGE, 638), T(perso, t, "propriete"), font=F("corpo", 14), fill=t["gris_f"])
    d.text((W - MARGE, 638), f"{T(perso, t, 'l_serie')} {perso['_serie']}",
           font=F("mono", 14), fill=t["gris_f"], anchor="ra")

    # Bande MRZ claire en pied
    my0 = 668
    d.rectangle([0, my0, W, H], fill=(232, 232, 228, 255))
    d.text((MARGE, my0 + 12), ligne_mrz(perso, T(perso, t, "mrz_prefixe", "WY")),
           font=F("mono", 20), fill=(22, 22, 22, 255))
    d.text((MARGE, my0 + 44), ligne_mrz2(perso, perso["_annee"]),
           font=F("mono", 20), fill=(22, 22, 22, 255))
    return arrondir_coins(img)

# ---------------------------------------------------------------------------
# THÈME 2 : SEEGSON — noir chaud / or / olive, rétro 70s
# ---------------------------------------------------------------------------
def seegson_recto(perso, t):
    img = nouvelle_face(t["fond"])
    rayures_diagonales_coin(img, "tr", [t["accent"], t["accent2"], (90, 76, 42, 255)])
    d = ImageDraw.Draw(img)
    fente_badge(d, W // 2, 22, contour=t["accent2"], fond=(0, 0, 0, 255))

    # Logo petit + en-tête
    logo = obtenir_logo(perso, "seegson", "petit", 150, 166, t)
    img.alpha_composite(logo, (MARGE, 58))
    d = ImageDraw.Draw(img)
    d.text((W - MARGE, 62), T(perso, t, "entete"), font=F("retro_m", 20),
           fill=t["accent2"], anchor="ra")
    d.text((W - MARGE, 96), f"{T(perso, t, 'l_id')} {perso['_id']}",
           font=F("mono_b", 26), fill=t["clair"], anchor="ra")
    texte_espace(d, (W - MARGE, 140), T(perso, t, "sous_entete"),
                 F("retro", 13), t["accent"], tracking=2, ancre="r")

    # Photo à gauche (optionnelle), cadre arrondi épais
    pw, ph = 230, 284
    px0, py0 = MARGE, 252
    if perso.get("photo"):
        photo = photo_ou_silhouette(perso, t, pw, ph)
        masque = Image.new("L", (pw, ph), 0)
        ImageDraw.Draw(masque).rounded_rectangle([0, 0, pw - 1, ph - 1], radius=22, fill=255)
        img.paste(photo, (px0, py0), masque)
        d.rounded_rectangle([px0 - 5, py0 - 5, px0 + pw + 5, py0 + ph + 5], radius=26,
                            outline=t["accent"], width=8)

    # Champs
    x = (px0 + pw + 40) if perso.get("photo") else MARGE
    lg = W - x - MARGE
    cl = t["accent2"]
    pl = F("retro_m", 15)
    champ(d, x, 248, T(perso, t, "l_nom"), perso["nom"].upper(), cl, t["clair"], pl, ("retro_b", 32), lg)
    champ(d, x, 320, T(perso, t, "l_prenom"), perso["prenom"], cl, t["clair"], pl, ("retro_b", 28), lg)
    champ(d, x, 390, T(perso, t, "l_fonction"), perso["profession"], cl, t["clair"], pl, ("retro_m", 25), lg)
    champ(d, x, 458, T(perso, t, "l_identifiant"), perso["username"], cl, t["accent2"], pl, ("mono_b", 25), lg)

    # Habilitation en barres rétro (colonne droite)
    buffer = 300
    texte_espace(d, (318 + buffer, 534), T(perso, t, "l_habilitation"), pl, cl, tracking=3)
    pastilles_habilitation(d, 318 + buffer, 562, perso["_habilitation"], t["accent"],
                           t["inactif"], taille=42, ecart=12, forme="barre")

    # Division / site / dates (colonne gauche)
    d.text((MARGE, 552), f"{T(perso, t, 'l_division')} {perso['_secteur']}",
           font=F("mono", 15), fill=t["clair"])
    d.text((MARGE, 578), f"{T(perso, t, 'l_site')} {perso['_site']}",
           font=F("mono", 15), fill=t["accent2"])
    d.text((MARGE, 604), f"{T(perso, t, 'l_emis')} {perso['_emission']}   "
                         f"{T(perso, t, 'l_exp')} {perso['_expiration']}",
           font=F("mono", 14), fill=(150, 138, 104, 255))

    # Bandeau bas doré
    by0, by1 = 634, 690
    d.rounded_rectangle([MARGE, by0, W - MARGE, by1], radius=14, fill=t["accent"])
    texte_ajuste(d, (W // 2, (by0 + by1) // 2), T(perso, t, "bandeau"),
                 "retro_b", 25, W - 2 * MARGE - 40, (16, 12, 6, 255), ancre="mm")
    micro_texte(d, MARGE, H - 40, W - 2 * MARGE, T(perso, t, "micro"),
                (110, 96, 62, 255), taille=10)
    return arrondir_coins(img)

def seegson_verso(perso, t):
    img = nouvelle_face(t["fond"])
    rayures_diagonales_coin(img, "bl", [(90, 76, 42, 255), t["accent2"], t["accent"]])
    bande_magnetique(img, 54, 146, base=(34, 26, 16, 255), reflet=(62, 50, 32, 255))
    d = ImageDraw.Draw(img)

    logo = obtenir_logo(perso, "seegson", "grand", 300, 330, t)
    poser_logo_centre(img, logo, W // 2, 314)
    d = ImageDraw.Draw(img)

    flavor = perso.get("flavor") or T(perso, t, "sous_entete")
    texte_ajuste(d, (W // 2, 502), f"« {flavor} »", "ital", 22, W - 2 * MARGE - 80,
                 (196, 182, 140, 255), ancre="ma")

    # Boîte code — double bordure rétro
    bx0, bx1, by0, by1 = 225, W - 225, 592, 660
    texte_espace(d, (W // 2, 560), T(perso, t, "code_titre"), F("retro_m", 15),
                 t["accent2"], tracking=2, ancre="m")
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=16, outline=t["accent"], width=4)
    d.rounded_rectangle([bx0 + 8, by0 + 8, bx1 - 8, by1 - 8], radius=10,
                        outline=t["accent2"], width=2)
    texte_ajuste(d, ((bx0 + bx1) // 2, (by0 + by1) // 2 + 2), str(perso["password"]),
                 "mono_b", 36, bx1 - bx0 - 60, t["clair"], ancre="mm")

    code_barres(d, 320, 690, 240, 26, perso["_rng"], t["accent2"])
    d.text((W - MARGE, 688), T(perso, t, "propriete"), font=F("retro", 13),
           fill=t["accent2"], anchor="ra")
    d.text((W - MARGE, 712), f"{T(perso, t, 'l_serie')} {perso['_serie']}",
           font=F("mono", 14), fill=t["accent"], anchor="ra")
    return arrondir_coins(img)

# ---------------------------------------------------------------------------
# THÈME 3 : PRODIGY — papier clair / noir, monochrome
# ---------------------------------------------------------------------------
def prodigy_recto(perso, t):
    img = nouvelle_face(t["fond"])
    maillage_hexagonal(img, 0, 64, W, H - 52, (60, 60, 58), alpha=16, taille=56)
    d = ImageDraw.Draw(img)

    # Bandeau noir supérieur
    d.rectangle([0, 0, W, 64], fill=t["noir"])
    texte_espace(d, (MARGE, 18), T(perso, t, "entete"), F("mono_b", 22),
                 t["blanc"], tracking=4)
    texte_espace(d, (W - MARGE, 20), T(perso, t, "sous_entete"), F("mono", 17),
                 (170, 170, 166, 255), tracking=2, ancre="r")

    # Logo petit + pilule ID
    logo = obtenir_logo(perso, "prodigy", "petit", 170, 158, t)
    img.alpha_composite(logo, (MARGE, 86))
    d = ImageDraw.Draw(img)
    ix0, iy0, ix1, iy1 = 252, 100, 646, 148
    d.rounded_rectangle([ix0, iy0, ix1, iy1], radius=24, outline=t["noir"], width=3)
    texte_ajuste(d, ((ix0 + ix1) // 2, (iy0 + iy1) // 2 + 1),
                 f"{T(perso, t, 'l_id')} {perso['_id']}", "mono_b", 24,
                 ix1 - ix0 - 36, t["noir"], ancre="mm")

    # Photo circulaire à droite (optionnelle)
    r = 122
    ccx, ccy = W - MARGE - 130, 296
    if perso.get("photo"):
        photo = photo_ou_silhouette(perso, t, 2 * r, 2 * r)
        masque = Image.new("L", (2 * r, 2 * r), 0)
        ImageDraw.Draw(masque).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
        img.paste(photo, (ccx - r, ccy - r), masque)
        d.ellipse([ccx - r, ccy - r, ccx + r, ccy + r], outline=t["noir"], width=5)
        for (dx, dy) in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            d.line([(ccx + dx * (r + 6), ccy + dy * (r + 6)),
                    (ccx + dx * (r + 24), ccy + dy * (r + 24))], fill=t["noir"], width=4)

    # Champs en colonne
    y0, pas = 268, 72
    lg = 660 if perso.get("photo") else (W - 2 * MARGE)
    cl = t["gris"]
    pl = F("mono", 14)
    for i, (lab, val, pol, tail) in enumerate([
            ("l_nom", perso["nom"].upper(), "retro_m", 30),
            ("l_prenom", perso["prenom"], "retro_m", 28),
            ("l_fonction", perso["profession"], "retro", 25),
            ("l_identifiant", perso["username"], "mono_b", 24)]):
        y = y0 + i * pas
        texte_espace(d, (MARGE, y), T(perso, t, lab), pl, cl, tracking=3)
        texte_ajuste(d, (MARGE, y + 22), str(val), pol, tail, lg, t["noir"])
        d.line([(MARGE, y + pas - 8), (MARGE + lg, y + pas - 8)], fill=t["regle"], width=2)

    # Habilitation
    texte_espace(d, (MARGE, 580), T(perso, t, "l_habilitation"), pl, cl, tracking=3)
    pastilles_habilitation(d, 252, 572, perso["_habilitation"], t["noir"],
                           t["regle"], taille=24, ecart=10)

    # Bandeau noir inférieur
    d.rectangle([0, H - 52, W, H], fill=t["noir"])
    texte_ajuste(d, (W // 2, H - 26), T(perso, t, "pied"), "mono", 14,
                 W - 2 * MARGE, (208, 208, 204, 255), ancre="mm")
    return arrondir_coins(img)

def prodigy_verso(perso, t):
    img = nouvelle_face(t["fond"])
    maillage_hexagonal(img, 0, 64, W, H - 52, (60, 60, 58), alpha=12, taille=64)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 64], fill=t["noir"])
    texte_espace(d, (W // 2, 18), T(perso, t, "raison"), F("mono_b", 22),
                 t["blanc"], tracking=5, ancre="m")

    logo = obtenir_logo(perso, "prodigy", "grand", 360, 330, t)
    poser_logo_centre(img, logo, W // 2, 252)
    d = ImageDraw.Draw(img)

    flavor = perso.get("flavor") or T(perso, t, "raison")
    texte_ajuste(d, (W // 2, 440), f"« {flavor} »", "ital", 22, W - 2 * MARGE - 60,
                 (86, 84, 80, 255), ancre="ma")

    # Boîte code
    bx0, bx1, by0, by1 = 225, W - 225, 532, 600
    texte_espace(d, (W // 2, 500), T(perso, t, "code_titre"), F("mono", 14),
                 t["noir"], tracking=2, ancre="m")
    d.rectangle([bx0, by0, bx1, by1], fill=t["blanc"], outline=t["noir"], width=3)
    texte_ajuste(d, ((bx0 + bx1) // 2, (by0 + by1) // 2 + 1), str(perso["password"]),
                 "mono_b", 36, bx1 - bx0 - 48, t["noir"], ancre="mm")

    # Dates + série
    d.text((MARGE, 630), f"{T(perso, t, 'l_emis')} {perso['_emission']}",
           font=F("mono", 16), fill=t["noir"])
    d.text((MARGE, 658), f"{T(perso, t, 'l_exp')}  {perso['_expiration']}",
           font=F("mono", 16), fill=t["noir"])
    d.text((W - MARGE, 632), f"{T(perso, t, 'l_serie')} {perso['_serie']}",
           font=F("mono", 15), fill=t["gris"], anchor="ra")

    d.rectangle([0, H - 52, W, H], fill=t["noir"])
    texte_ajuste(d, (W // 2, H - 26), T(perso, t, "propriete"), "mono", 14,
                 W - 2 * MARGE, (208, 208, 204, 255), ancre="mm")
    return arrondir_coins(img)

# ---------------------------------------------------------------------------
# THÈME 4 : LASALLE BIONATIONAL — nuit / bleu acier / gris
# ---------------------------------------------------------------------------
def lasalle_recto(perso, t):
    img = nouvelle_face(t["fond"])
    double_helice(img, W - 78, 140, 560, 54, t["accent"], alpha=42, periodes=2.4)
    chevrons_danger(img, 0, 40, t["sombre"], t["accent"])
    d = ImageDraw.Draw(img)

    # Logo petit + en-tête
    logo = obtenir_logo(perso, "lasalle", "petit", 205, 152, t)
    img.alpha_composite(logo, (MARGE, 58))
    d = ImageDraw.Draw(img)
    d.text((W - MARGE, 70), T(perso, t, "entete"), font=F("cond_b", 25),
           fill=t["accent2"], anchor="ra")
    texte_espace(d, (W - MARGE, 108), T(perso, t, "sous_entete"), F("cond", 15),
                 t["gris"], tracking=2, ancre="r")
    d.rectangle([W - MARGE - 124, 140, W - MARGE, 178], outline=t["accent"], width=3)
    d.text((W - MARGE - 62, 159), f"{T(perso, t, 'l_gs')} {perso['_sang']}",
           font=F("mono_b", 20), fill=t["accent2"], anchor="mm")

    # Photo à gauche (optionnelle) avec réticule
    pw, ph = 230, 284
    px0, py0 = MARGE, 238
    if perso.get("photo"):
        img.paste(photo_ou_silhouette(perso, t, pw, ph), (px0, py0))
        d.rectangle([px0, py0, px0 + pw, py0 + ph], outline=(30, 52, 64, 255), width=2)
        crochets_reticule(d, px0 - 8, py0 - 8, px0 + pw + 8, py0 + ph + 8,
                          lg=28, ep=5, fill=t["accent"])

    # Champs
    x = (px0 + pw + 40) if perso.get("photo") else MARGE
    lg = W - x - MARGE
    cl = t["accent"]
    pl = F("cond", 16)
    champ(d, x, 236, T(perso, t, "l_nom"), perso["nom"].upper(), cl, t["clair"], pl, ("cond_b", 33), lg)
    champ(d, x, 306, T(perso, t, "l_prenom"), perso["prenom"], cl, t["clair"], pl, ("cond_b", 29), lg)
    champ(d, x, 374, T(perso, t, "l_fonction"), perso["profession"], cl, t["clair"], pl, ("cond_b", 26), lg)
    champ(d, x, 442, T(perso, t, "l_identifiant"), perso["username"], cl, t["accent2"], pl, ("mono_b", 24), lg)

    # Bandeau habilitation : libellé + jauge hexagonale
    by0, by1 = 548, 600
    d.rectangle([0, by0, W, by1], fill=t["accent"])
    texte_ajuste(d, (MARGE + 4, (by0 + by1) // 2 + 1), T(perso, t, "l_habilitation"),
                 "cond_b", 26, 690, (5, 12, 16, 255), ancre="lm")
    pastilles_habilitation(d, W - MARGE - (5 * 30 + 4 * 10), by0 + 11,
                           perso["_habilitation"], (6, 14, 20, 255),
                           (104, 168, 188, 255), taille=30, ecart=10, forme="hex")

    # Division / site / dates + ID
    d.text((MARGE, 618), f"{T(perso, t, 'l_division')} {perso['_secteur']}",
           font=F("mono", 15), fill=t["clair"])
    d.text((MARGE, 644), f"{T(perso, t, 'l_site')} {perso['_site']}",
           font=F("mono", 15), fill=t["accent2"])
    d.text((MARGE, 670), f"{T(perso, t, 'l_emis')} {perso['_emission']}   "
                         f"{T(perso, t, 'l_exp')} {perso['_expiration']}",
           font=F("mono", 14), fill=(120, 150, 164, 255))
    texte_espace(d, (642, 614), T(perso, t, "l_id"), F("cond", 15), cl, tracking=3)
    d.text((642, 636), str(perso["_id"]), font=F("mono_b", 36), fill=t["accent2"])

    micro_texte(d, MARGE, H - 38, W - 2 * MARGE, T(perso, t, "micro"),
                (70, 100, 116, 255), taille=10)
    d.rectangle([0, H - 20, W, H - 16], fill=t["accent"])
    return arrondir_coins(img)

def lasalle_verso(perso, t):
    img = nouvelle_face(t["fond"])
    double_helice(img, 98, 170, 590, 52, t["accent"], alpha=38, periodes=2.4)
    bande_magnetique(img, 54, 146, base=(14, 22, 30, 255), reflet=(34, 50, 62, 255))
    d = ImageDraw.Draw(img)
    d.line([(0, 150), (W, 150)], fill=t["accent"], width=3)

    logo = obtenir_logo(perso, "lasalle", "grand", 390, 282, t)
    poser_logo_centre(img, logo, W // 2, 298)
    d = ImageDraw.Draw(img)

    flavor = perso.get("flavor") or T(perso, t, "sous_entete")
    texte_ajuste(d, (W // 2, 466), f"« {flavor} »", "ital", 22, W - 2 * MARGE - 80,
                 (168, 190, 200, 255), ancre="ma")

    # Boîte code bordure bleue
    bx0, bx1, by0, by1 = 230, W - 230, 556, 624
    texte_espace(d, (W // 2, 524), T(perso, t, "code_titre"), F("mono", 15),
                 t["accent2"], tracking=3, ancre="m")
    d.rectangle([bx0, by0, bx1, by1], fill=(4, 9, 14, 255), outline=t["accent"], width=4)
    texte_ajuste(d, ((bx0 + bx1) // 2, (by0 + by1) // 2 + 1), str(perso["password"]),
                 "mono_b", 34, bx1 - bx0 - 44, t["clair"], ancre="mm")

    d.text((MARGE, 648), f"{T(perso, t, 'l_emis')} {perso['_emission']}",
           font=F("mono", 15), fill=t["accent2"])
    d.text((MARGE, 674), f"{T(perso, t, 'l_exp')}  {perso['_expiration']}",
           font=F("mono", 15), fill=t["accent2"])
    d.text((W - MARGE, 648), f"{T(perso, t, 'l_serie')} {perso['_serie']}",
           font=F("mono", 15), fill=t["accent2"], anchor="ra")
    d.text((W - MARGE, 674), T(perso, t, "propriete"), font=F("cond", 14),
           fill=(110, 140, 154, 255), anchor="ra")

    chevrons_danger(img, H - 44, H - 12, t["sombre"], t["accent"])
    return arrondir_coins(img)

RENDUS = {
    "wy": (wy_recto, wy_verso),
    "seegson": (seegson_recto, seegson_verso),
    "prodigy": (prodigy_recto, prodigy_verso),
    "lasalle": (lasalle_recto, lasalle_verso),
}

# ---------------------------------------------------------------------------
# PDF D'IMPRESSION (A4, 3x3 cartes, recto/verso "retourner sur les bords longs")
# ---------------------------------------------------------------------------
def construire_pdf(paires, chemin_pdf):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader

    page_w, page_h = A4
    cols, ligs = 2, 4
    par_page = cols * ligs
    cw, ch = CARD_W_MM * mm, CARD_H_MM * mm
    gouttiere = 6 * mm
    total_w = cols * cw + (cols - 1) * gouttiere
    total_h = ligs * ch + (ligs - 1) * gouttiere
    mx = (page_w - total_w) / 2
    my = (page_h - total_h) / 2

    def pos(idx, miroir=False):
        col, lig = idx % cols, idx // cols
        if miroir:
            col = cols - 1 - col
        x = mx + col * (cw + gouttiere)
        y = page_h - my - (lig + 1) * ch - lig * gouttiere
        return x, y

    def traits_coupe(c, x, y):
        c.setLineWidth(0.4)
        c.setStrokeColorRGB(0.45, 0.45, 0.45)
        t, o = 3 * mm, 0.8 * mm
        for (px, py, dx, dy) in [(x, y, -1, -1), (x + cw, y, 1, -1),
                                 (x, y + ch, -1, 1), (x + cw, y + ch, 1, 1)]:
            c.line(px + dx * o, py, px + dx * (o + t), py)
            c.line(px, py + dy * o, px, py + dy * (o + t))

    c = rl_canvas.Canvas(chemin_pdf, pagesize=A4)
    for debut in range(0, len(paires), par_page):
        lot = paires[debut:debut + par_page]
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(mx, page_h - 6 * mm,
                     f"RECTOS — feuille {debut // par_page + 1} — imprimer à 100 %, recto/verso « bord long »")
        for i, (recto, _) in enumerate(lot):
            x, y = pos(i)
            c.drawImage(ImageReader(recto), x, y, cw, ch, mask="auto")
            traits_coupe(c, x, y)
        c.showPage()
        c.setFont("Helvetica", 7)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(mx, page_h - 6 * mm, f"VERSOS — feuille {debut // par_page + 1}")
        for i, (_, verso) in enumerate(lot):
            x, y = pos(i, miroir=True)
            c.drawImage(ImageReader(verso), x, y, cw, ch, mask="auto")
            traits_coupe(c, x, y)
        c.showPage()
    c.save()

# ---------------------------------------------------------------------------
# APERÇU (montage de toutes les faces)
# ---------------------------------------------------------------------------
def construire_apercu(faces, chemin, echelle=0.30):
    sw, sh = int(W * echelle), int(H * echelle)
    pad, entete, ecart = 26, 48, 12
    paire_w = 2 * sw + ecart
    cols = 2
    ligs = (len(faces) + cols - 1) // cols
    largeur = pad + cols * (paire_w + pad)
    hauteur = pad + ligs * (sh + entete + pad)
    planche = Image.new("RGBA", (largeur, hauteur), (24, 24, 28, 255))
    d = ImageDraw.Draw(planche)
    for i, (titre, recto, verso) in enumerate(faces):
        col, lig = i % cols, i // cols
        x = pad + col * (paire_w + pad)
        y = pad + lig * (sh + entete + pad)
        d.text((x, y + 4), titre, font=F("mono_b", 22), fill=(230, 230, 230, 255))
        y += entete
        planche.alpha_composite(recto.resize((sw, sh), Image.LANCZOS), (x, y))
        planche.alpha_composite(verso.resize((sw, sh), Image.LANCZOS), (x + sw + ecart, y))
    planche.convert("RGB").save(chemin)

# ---------------------------------------------------------------------------
# PROGRAMME PRINCIPAL
# ---------------------------------------------------------------------------
def normaliser_compagnie(nom):
    cle = NORMALISATION.get(str(nom).strip().lower())
    if not cle:
        raise ValueError(f"Compagnie inconnue : {nom!r} "
                         f"(attendu : weyland-yutani, seegson, prodigy, lasalle)")
    return cle

def fusionner_textes(theme, racine, perso, cle):
    t = dict(theme)
    textes = dict(theme["textes"])
    textes.update(racine.get("textes_compagnies", {}).get(cle, {}))
    textes.update(perso.get("textes", {}))
    t["textes"] = textes
    return t

def main():
    fichier = sys.argv[1] if len(sys.argv) > 1 else "personnages.json"
    with open(fichier, encoding="utf-8") as f:
        donnees = json.load(f)
    annee = int(donnees.get("annee", ANNEE_DEFAUT))
    persos = donnees["personnages"]

    os.makedirs(DOSSIER_SORTIE, exist_ok=True)
    paires, faces_apercu = [], []
    for p in persos:
        cle = normaliser_compagnie(p["compagnie"])
        p = generer_donnees(dict(p), cle, annee)
        p["_annee"] = annee
        theme = fusionner_textes(THEMES[cle], donnees, p, cle)
        fr, fv = RENDUS[cle]
        recto, verso = fr(p, theme), fv(p, theme)
        base = sans_accents(f"{p['nom']}_{p['prenom']}").replace(" ", "-")
        cr = os.path.join(DOSSIER_SORTIE, f"{base}_recto.png")
        cv = os.path.join(DOSSIER_SORTIE, f"{base}_verso.png")
        recto.save(cr, dpi=(DPI, DPI))
        verso.save(cv, dpi=(DPI, DPI))
        paires.append((cr, cv))
        faces_apercu.append((f"{theme['textes']['raison']} — {p['prenom']} {p['nom']}",
                             recto, verso))
        print(f"  [ok] {theme['textes']['raison']:<22} {p['prenom']} {p['nom']}  ({p['_id']})")

    pdf = os.path.join(DOSSIER_SORTIE, "planche_impression.pdf")
    construire_pdf(paires, pdf)
    apercu = os.path.join(DOSSIER_SORTIE, "apercu.png")
    construire_apercu(faces_apercu, apercu)
    print(f"\n{len(persos)} carte(s) générée(s) dans ./{DOSSIER_SORTIE}/ (88 x 63 mm)")
    print(f"  - {pdf} (imprimer à 100 %, recto/verso « bord long »)")
    print(f"  - {apercu}")

if __name__ == "__main__":
    main()
