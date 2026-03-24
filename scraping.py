"""
Scraper Top 14 - Résultats par saison
Export JSON avec : score, bonus, classement, lien feuille de match
"""

import json
import time
import requests
from bs4 import BeautifulSoup
import csv

# ─── CONFIG ───────────────────────────────────────────────────────────────────

SAISON = "2020-2021"   # ← change ici (ex: "2024-2025")
BASE_URL = "https://top14.lnr.fr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}
DELAI_ENTRE_REQUETES = 2  # secondes
OUTPUT_FILE = f"top14_{SAISON}.json"

# ─── FONCTIONS ────────────────────────────────────────────────────────────────

def get_page(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  ⚠️  Erreur lors du chargement de {url} : {e}")
        return None


def get_journees(saison: str) -> list:
    """Récupère la liste des slugs de journées pour la saison via le JSON embarqué."""
    url = f"{BASE_URL}/calendrier-et-resultats/{saison}/j1"
    soup = get_page(url)
    if not soup:
        return []

    filters_tag = soup.find("filters-fixtures")
    if not filters_tag:
        print("  ⚠️  Impossible de trouver le composant filters-fixtures")
        return []

    raw = filters_tag.get(":filter-list", "{}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("  ⚠️  Impossible de parser le JSON des filtres")
        return []

    seasons = data.get("seasons", [])
    season_id = None
    for s in seasons:
        if s["name"] == saison:
            season_id = str(s["id"])
            break

    if season_id is None:
        print(f"  ⚠️  Saison '{saison}' introuvable dans les filtres")
        return []

    weeks = data.get("weeks", {}).get(season_id, [])
    return [w["slug"] for w in weeks]


def parse_journee(soup, journee_slug: str) -> list:
    matches = []
    current_date = None

    for element in soup.select(
        ".calendar-results__fixture-date, .calendar-results__line"
    ):
        classes = element.get("class", [])

        if "calendar-results__fixture-date" in classes:
            current_date = element.get_text(strip=True)
            continue

        if "calendar-results__line" not in classes:
            continue

        clubs = element.select(".club-line__name")
        score_tag = element.select_one("a.match-line__score")
        str_score = score_tag.get_text(strip=True)
        dom_score, ext_score = str_score.split(" - ") if " - " in str_score else (None, None)
        ranks = element.select(".club-line__rank")

        if len(clubs) < 2 or not score_tag:
            continue

        bonus_tags = element.select(".match-line__club-special-icon--active")
        bonus_home = bonus_away = None
        result_left = element.select_one(".match-line__result--left")
        result_right = element.select_one(".match-line__result--right")

        for bt in bonus_tags:
            val = bt.get_text(strip=True)
            if result_left and bt in result_left.descendants:
                bonus_home = val
            elif result_right and bt in result_right.descendants:
                bonus_away = val

        match = {
            "journee": journee_slug,
            "date": current_date,
            "domicile": {
                "nom": clubs[0].get_text(strip=True),
                "classement": ranks[0].get_text(strip=True) if ranks else None,
                "bonus": bonus_home,
                "score": dom_score,
            },
            "exterieur": {
                "nom": clubs[1].get_text(strip=True),
                "classement": ranks[1].get_text(strip=True) if len(ranks) > 1 else None,
                "bonus": bonus_away,
                "score": ext_score,
            },
            "score": score_tag.get_text(strip=True),
            "lien_feuille_match": score_tag["href"],
        }
        matches.append(match)

    return matches

def parse_stats_match(soup) -> dict:
    """
    Extrait les stats collectives (stats-bar) et les événements (game-facts)
    depuis la page statistiques-du-match.
    """
    stats = {}

    # ── Stats collectives (barres) ─────────────────────────────────────────
    for bar in soup.select(".stats-bar"):
        titre = bar.select_one(".stats-bar__title")
        val_left = bar.select_one(".stats-bar__val--left")
        val_right = bar.select_one(".stats-bar__val--right")
        if titre and val_left and val_right:
            stats[titre.get_text(strip=True)] = {
                "domicile": val_left.get_text(strip=True),
                "exterieur": val_right.get_text(strip=True),
            }

    # ── Cartons (blocs séparés des barres) ────────────────────────────────
    cards_teams = soup.select(".match-statistics__cards-team")
    for i, team_key in enumerate(["domicile", "exterieur"]):
        if i >= len(cards_teams):
            break
        for card in cards_teams[i].select(".stats-cards-fault"):
            couleur = next(
                (c.replace("stats-cards-fault--", "")
                 for c in card.get("class", [])
                 if "stats-cards-fault--" in c and c != "stats-cards-fault"),
                None
            )
            val = card.select_one(".stats-cards-fault__card")
            if couleur and val:
                key = f"Carton {couleur}"
                if key not in stats:
                    stats[key] = {"domicile": None, "exterieur": None}
                stats[key][team_key] = val.get_text(strip=True)

    # # ── Événements du match (game-facts JSON) ─────────────────────────────
    # timeline_tag = soup.find("header-timeline")
    # events = []
    # if timeline_tag:
    #     raw = timeline_tag.get(":game-facts", "[]")
    #     try:
    #         facts = json.loads(raw)
    #         for f in facts:
    #             player = f.get("player", {})
    #             conv = f.get("conversionPlayer")
    #             events.append({
    #                 "minute":    f.get("minute"),
    #                 "type":      f.get("type"),
    #                 "sous_type": f.get("subtype"),
    #                 "equipe":    f.get("club"),       # "home" ou "away"
    #                 "score":     f.get("score"),       # [dom, ext] après l'action
    #                 "joueur":    f"{player.get('firstName', '')} {player.get('lastName', '')}".strip(),
    #                 "transformateur": (
    #                     f"{conv['firstName']} {conv['lastName']}".strip()
    #                     if conv else None
    #                 ),
    #             })
    #     except json.JSONDecodeError:
    #         pass

    # # ── Stats joueurs (players-ranking JSON) ──────────────────────────────
    # joueurs = {"domicile": [], "exterieur": []}
    # ranking_tags = soup.select("players-ranking[\\:ranking]")
    # for idx, tag in enumerate(ranking_tags[:2]):
    #     team_key = "domicile" if idx == 0 else "exterieur"
    #     raw = tag.get(":ranking", "[]")
    #     try:
    #         players = json.loads(raw)
    #         for p in players:
    #             joueurs[team_key].append({
    #                 "nom":              p["player"]["name"],
    #                 "url":              p["player"]["url"],
    #                 "poste":            p.get("position"),
    #                 "minutes":          p.get("minutesPlayed"),
    #                 "points":           p.get("nbPoints"),
    #                 "essais":           p.get("nbEssais"),
    #                 "offloads":         p.get("offload"),
    #                 "franchissements":  p.get("lineBreak"),
    #                 "ballons_grattés":  p.get("breakdownSteals"),
    #                 "plaquages":        p.get("totalSuccessfulTackles"),
    #                 "cartons_jaunes":   p.get("nbCartonsJaunes"),
    #                 "cartons_oranges":  p.get("nbCartonsOranges"),
    #                 "cartons_rouges":   p.get("nbCartonsRouges"),
    #             })
    #     except json.JSONDecodeError:
    #         pass

    # return {"stats_collectives": stats, "evenements": events, "joueurs": joueurs}
    return {"stats_collectives": stats}


def scrape_stats_feuille(lien_feuille: str) -> dict:
    """Charge la page /statistiques-du-match et retourne les données parsées."""
    url = lien_feuille.rstrip("/") + "/statistiques-du-match"
    soup = get_page(url)
    if not soup:
        return {}
    return parse_stats_match(soup)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def scrape_saison(saison: str) -> list:
    print(f"\n🏉  Scraping Top 14 — saison {saison}\n{'─'*45}")

    journees = get_journees(saison)
    if not journees:
        print("Aucune journée trouvée, arrêt.")
        return []

    print(f"  {len(journees)} journées détectées : {', '.join(journees[:5])}…\n")

    tous_les_matchs = []

    for slug in journees:
        url = f"{BASE_URL}/calendrier-et-resultats/{saison}/{slug}"
        print(f"  → {slug}  ({url})")

        soup = get_page(url)
        if not soup:
            continue

        matchs = parse_journee(soup, slug)
        print(f"     {len(matchs)} match(s) trouvé(s)")
        matchs = parse_journee(soup, slug)
        for m in matchs:
            print(f"       ↳ stats {m['lien_feuille_match']}")
            m["statistiques"] = scrape_stats_feuille(m["lien_feuille_match"])
            time.sleep(DELAI_ENTRE_REQUETES)
   
        tous_les_matchs.extend(matchs)

        time.sleep(DELAI_ENTRE_REQUETES)

    return tous_les_matchs

from datetime import datetime

def parse_rugby_date(date_str, saison_str):
    # saison_str ex: "2019-2020" -> on prend 2019
    annee_depart = int(saison_str.split('-')[0])
    
    mois_map = {
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
        'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
    }
    
    try:
        # Nettoyage de la chaîne (ex: "samedi 25 août")
        parts = date_str.lower().split()
        jour = int(parts[1])
        mois = mois_map[parts[2]]
        
        # Si le mois est entre janvier (1) et juin (6), c'est l'année N+1 de la saison
        annee = annee_depart + 1 if mois <= 6 else annee_depart
        
        return datetime(annee, mois, jour).strftime("%d/%m/%Y")
    except:
        return date_str # Retourne la string brute en cas d'erreur
    
def export_csv_pivot(resultats, saison, filename):
    with open(filename, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "journee", "date_formatee", "equipe", "role", 
            "adversaire", "score_equipe", "score_adversaire", 
            "classement_avant_match", "bonus"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for m in resultats:
            date_clean = parse_rugby_date(m["date"], saison)
            
            # --- Ligne pour l'équipe DOMICILE ---
            writer.writerow({
                "journee": m["journee"],
                "date_formatee": date_clean,
                "equipe": m["domicile"]["nom"],
                "role": "Domicile",
                "adversaire": m["exterieur"]["nom"],
                "score_equipe": m["domicile"]["score"],
                "score_adversaire": m["exterieur"]["score"],
                "classement_avant_match": m["domicile"]["classement"].split("e")[0] if m["domicile"]["classement"] else None,
                "bonus": m["domicile"]["bonus"]
            })

            # --- Ligne pour l'équipe EXTÉRIEUR ---
            writer.writerow({
                "journee": m["journee"],
                "date_formatee": date_clean,
                "equipe": m["exterieur"]["nom"],
                "role": "Extérieur",
                "adversaire": m["domicile"]["nom"],
                "score_equipe": m["exterieur"]["score"],
                "score_adversaire": m["domicile"]["score"],
                "classement_avant_match": m["exterieur"]["classement"].split("e")[0] if m["exterieur"]["classement"] else None,
                "bonus": m["exterieur"]["bonus"]
            })


def main():
    resultats = scrape_saison(SAISON)

    output = {
        "saison": SAISON,
        "total_matchs": len(resultats),
        "matchs": resultats,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅  {len(resultats)} matchs exportés dans '{OUTPUT_FILE}'")

    # ── Export CSV Pivoté ──────────────────────────────────────────────────
    csv_file = OUTPUT_FILE.replace(".json", "_tableau.csv")
    export_csv_pivot(resultats, SAISON, csv_file)
    
    print(f"✅ CSV optimisé pour Tableau exporté dans '{csv_file}'")

if __name__ == "__main__":
    main()