import json
import csv
import sys
import re
from pathlib import Path
import uuid


STATS_COLS = [
    "Essais accordés",
    "Possession de la balle",
    "Occupation",
    "Possession dans son camp",
    "Possession dans le camp adverse",
    "Possession 22m adverses",
    "Mêlées obtenues",
    "Mêlées perdues",
    "Mêlées gagnées",
    "Mêlées refaites",
    "Touches obtenues",
    "Touches gagnées sur son propre lancer",
    "Touches gagnées sur lancer adverse",
    "En-avant commis",
    "Pénalités réussies",
    "Pénalités concédées",
    "Plaquages réussis",
    "Plaquages offensifs réussis",
    "Plaquages manqués",
    "Ballons joués au pied",
    "Ballons passés",
    "Carton yellow",
    "Carton orange",
    "Carton red",
]

STAT_RENAME = {
    "Essais accordés": "essais_accordes",
    "Possession de la balle": "possession_balle",
    "Occupation": "occupation",
    "Possession dans son camp": "possession_prop_camp",
    "Possession dans le camp adverse": "possession_camp_adv",
    "Possession 22m adverses": "possession_22m_adv",
    "Mêlées obtenues": "melees_obtenues",
    "Mêlées perdues": "melees_perdues",
    "Mêlées gagnées": "melees_gagnees",
    "Mêlées refaites": "melees_refaites",
    "Touches obtenues": "touches_obtenues",
    "Touches gagnées sur son propre lancer": "touches_propre_lancer",
    "Touches gagnées sur lancer adverse": "touches_lancer_adv",
    "En-avant commis": "en_avant_commis",
    "Pénalités réussies": "penalites_reussies",
    "Pénalités concédées": "penalites_concedees",
    "Plaquages réussis": "plaquages_reussis",
    "Plaquages offensifs réussis": "plaquages_offensifs",
    "Plaquages manqués": "plaquages_manques",
    "Ballons joués au pied": "ballons_pied",
    "Ballons passés": "ballons_passes",
    "Carton yellow": "carton_jaune",
    "Carton orange": "carton_orange",
    "Carton red": "carton_rouge",
}

MOIS = {
    "janvier": "01", "février": "02", "mars": "03", "avril": "04",
    "mai": "05", "juin": "06", "juillet": "07", "août": "08",
    "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12",
}


def format_date(raw: str, season: str) -> str:
    """
    Convertit 'samedi 29 février 2020' → '29/02/2020'.
    Gère aussi les dates sans année (suppose 2019-2020).
    """
    if not raw:
        return ""
    parts = raw.strip().split()
    # parts = [jour_semaine, num, mois, ?année]
    try:
        day = parts[1].zfill(2)
        month = MOIS.get(parts[2].lower(), "??")
        # Année absente dans certaines saisons : on déduit selon le mois
        season_start_year = season.split("-")[0]
        season_end_year = season.split("-")[1]
        if month in ("01", "02", "03", "04", "05", "06"):
            year = season_end_year
        else:
            year = season_start_year
        return f"{day}/{month}/{year}"
    except IndexError:
        return raw


def extract_matchs(data: dict | list, season: str) -> list:
    """Accepte le JSON brut ou directement une liste de matchs."""
    if isinstance(data, list):
        return data
    for v in data.values():
        if isinstance(v, list):
            return v
    raise ValueError("Impossible de trouver la liste de matchs dans le JSON.")


def build_rows(matchs: list, season: str) -> list[dict]:
    rows = []

    for m in matchs:
        id = uuid.uuid4().hex[:8]  # ID unique court pour chaque match
        stats = (m.get("statistiques") or {}).get("stats_collectives") or {}

        date_fmt = format_date(m.get("date", ""), season)
        journee = m.get("journee", "")

        for role in ("domicile", "exterieur"):
            is_home = role == "domicile"
            adv_role = "exterieur" if is_home else "domicile"

            eq = m.get(role) or {}
            adv = m.get(adv_role) or {}

            score_eq = int(eq.get("score", 0) or 0)
            score_adv = int(adv.get("score", 0) or 0)

            if score_eq > score_adv:
                resultat = "Victoire"
            elif score_eq < score_adv:
                resultat = "Défaite"
            else:
                resultat = "Nul"

            row = {
                "id": str(id),
                "journee": journee,
                "date_formatee": date_fmt,
                "equipe": eq.get("nom", ""),
                "role": "Domicile" if is_home else "Extérieur",
                "adversaire": adv.get("nom", ""),
                "score_equipe": eq.get("score", ""),
                "score_adversaire": adv.get("score", ""),
                "classement_avant_match": eq.get("classement", ""),
                "bonus": eq.get("bonus") or "",
                "resultat": resultat,
            }

            for stat_key in STATS_COLS:
                col_name = STAT_RENAME[stat_key]
                stat_obj = stats.get(stat_key)
                row[col_name] = stat_obj.get(role, "") if stat_obj else ""

            rows.append(row)

    return rows


def json_to_csv(input_paths: list, output_path: str) -> None:
    all_rows = []

    for input_path in input_paths:
        input_file = Path(input_path)
        if not input_file.exists():
            print(f"Erreur : fichier introuvable → {input_path}")
            sys.exit(1)

        with open(input_file, encoding="utf-8") as f:
            data = json.load(f)

        season = data.get("saison", "saison_inconnue")
        matchs = extract_matchs(data, season)
        rows = build_rows(matchs, season)
        all_rows.extend(rows)

        if not rows:
            print("Aucun match trouvé dans le JSON.")
            sys.exit(1)

    fieldnames = list(all_rows[0].keys())

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"CSV généré : {output_file}")


if __name__ == "__main__":
    files = [
        "top14_2016-2017.json",
        "top14_2017-2018.json",
        "top14_2018-2019.json",
        "top14_2019-2020.json",
    ]
    
    output_csv = "top14_stats.csv"
    json_to_csv(files, output_csv)
    
    print("Terminé.")

    