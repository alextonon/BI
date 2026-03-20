import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


# Colonnes numériques à moyenner
NUMERIC_COLS = [
    "score_equipe", "score_adversaire",
    "essais_accordes",
    "melees_obtenues", "melees_perdues", "melees_gagnees", "melees_refaites",
    "touches_obtenues", "touches_propre_lancer", "touches_lancer_adv",
    "en_avant_commis",
    "penalites_reussies", "penalites_concedees",
    "plaquages_reussis", "plaquages_offensifs", "plaquages_manques",
    "ballons_pied", "ballons_passes",
    "carton_jaune", "carton_orange", "carton_rouge",
]

# Colonnes pourcentage (ex: "50 %") → extraire le nombre
PCT_COLS = [
    "possession_balle", "occupation",
    "possession_prop_camp", "possession_camp_adv", "possession_22m_adv",
]


def parse_pct(val: str) -> float | None:
    """'50 %' → 50.0, '' → None"""
    if not val:
        return None
    m = re.search(r"[\d.]+", val)
    return float(m.group()) if m else None


def parse_num(val: str) -> float | None:
    if val == "" or val is None:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def infer_season(journee: str, date: str) -> str:
    """
    Déduit la saison depuis la date (format JJ/MM/AAAA).
    Une saison Top14 chevauche deux années civiles (ex: 2019-2020).
    Mois 1-6 → saison N-1/N, mois 7-12 → saison N/N+1.
    """
    try:
        parts = date.split("/")
        month = int(parts[1])
        year = int(parts[2])
        if month >= 7:
            return f"{year}-{year + 1}"
        else:
            return f"{year - 1}-{year}"
    except Exception:
        return "inconnue"


class TeamAccumulator:
    def __init__(self):
        self.n = 0
        self.victoires = 0
        self.defaites = 0
        self.nuls = 0
        self.bonus_bo = 0
        self.bonus_bd = 0
        self.numeric_sums = defaultdict(float)
        self.numeric_counts = defaultdict(int)
        self.pct_sums = defaultdict(float)
        self.pct_counts = defaultdict(int)

    def add(self, row: dict):
        self.n += 1
        r = row.get("resultat", "")
        if r == "Victoire":
            self.victoires += 1
        elif r == "Défaite":
            self.defaites += 1
        elif r == "Nul":
            self.nuls += 1

        bonus = row.get("bonus", "")
        if bonus == "Bo":
            self.bonus_bo += 1
        elif bonus == "Bd":
            self.bonus_bd += 1

        for col in NUMERIC_COLS:
            v = parse_num(row.get(col, ""))
            if v is not None:
                self.numeric_sums[col] += v
                self.numeric_counts[col] += 1

        for col in PCT_COLS:
            v = parse_pct(row.get(col, ""))
            if v is not None:
                self.pct_sums[col] += v
                self.pct_counts[col] += 1

    def to_dict(self, equipe: str, extra: dict = None) -> dict:
        row = {"equipe": equipe}
        if extra:
            row.update(extra)
        row["matchs_joues"] = self.n
        row["victoires"] = self.victoires
        row["defaites"] = self.defaites
        row["nuls"] = self.nuls
        row["taux_victoire_pct"] = round(self.victoires / self.n * 100, 1) if self.n else ""
        row["bonus_offensif"] = self.bonus_bo
        row["bonus_defensif"] = self.bonus_bd

        for col in NUMERIC_COLS:
            cnt = self.numeric_counts[col]
            row[f"moy_{col}"] = round(self.numeric_sums[col] / cnt, 2) if cnt else ""

        for col in PCT_COLS:
            cnt = self.pct_counts[col]
            row[f"moy_{col}"] = round(self.pct_sums[col] / cnt, 1) if cnt else ""

        return row


def build_fieldnames(extra_keys: list[str]) -> list[str]:
    base = ["equipe"] + extra_keys + [
        "matchs_joues", "victoires", "defaites", "nuls",
        "taux_victoire_pct", "bonus_offensif", "bonus_defensif",
    ]
    for col in NUMERIC_COLS:
        base.append(f"moy_{col}")
    for col in PCT_COLS:
        base.append(f"moy_{col}")
    return base


def write_csv(path: str, rows: list[dict], fieldnames: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  → {path}  ({len(rows)} lignes)")


def aggregate(input_path: str):
    src = Path(input_path)
    if not src.exists():
        print(f"Fichier introuvable : {input_path}")
        sys.exit(1)

    # Accumulateurs
    all_seasons: dict[str, TeamAccumulator] = defaultdict(TeamAccumulator)
    by_season: dict[tuple[str, str], TeamAccumulator] = defaultdict(TeamAccumulator)

    with open(src, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            equipe = row.get("equipe", "").strip()
            if not equipe:
                continue
            saison = infer_season(row.get("journee", ""), row.get("date_formatee", ""))

            all_seasons[equipe].add(row)
            by_season[(saison, equipe)].add(row)

    # --- Fichier 1 : toutes saisons confondues ---
    out_global = src.parent / (src.stem + "_moy_global.csv")
    fieldnames_global = build_fieldnames([])
    rows_global = sorted(
        [acc.to_dict(eq) for eq, acc in all_seasons.items()],
        key=lambda r: r["equipe"],
    )
    write_csv(str(out_global), rows_global, fieldnames_global)

    # --- Fichier 2 : une ligne par (saison, équipe) ---
    out_saison = src.parent / (src.stem + "_moy_par_saison.csv")
    fieldnames_saison = build_fieldnames(["saison"])
    rows_saison = sorted(
        [acc.to_dict(eq, {"saison": sai}) for (sai, eq), acc in by_season.items()],
        key=lambda r: (r["saison"], r["equipe"]),
    )
    write_csv(str(out_saison), rows_saison, fieldnames_saison)

    print(f"\nTerminé : {len(all_seasons)} équipes, {len(set(k[0] for k in by_season))} saisons.")


if __name__ == "__main__":
    csv_path = "top14_stats.csv"
    
    aggregate(csv_path)