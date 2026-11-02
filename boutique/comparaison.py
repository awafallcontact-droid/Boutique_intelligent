"""Palier 2b : agent seul vs multi-agents sur les 3 mêmes demandes.

Les 3 demandes retenues sont celles de l'énoncé dont le résultat attendu est chiffré :
rupture du sac (palier 1, test 3), scénario Afi (palier 2a), scénario Koffi (palier 2b).
Aucune ne crée de commande : la comparaison ne demande pas de validation humaine."""
import re
import tempfile
import time
from pathlib import Path

import requests

from . import config
from .donnees import Boutique, normaliser
from .equipe import Equipe
from .trace import Trace
from .vendeur_seul import creer_vendeur_seul


def nombres(texte: str) -> list[float]:
    """Extrait 46 000 / 46.000 / 46000 / 30 869,80 / 30,869.80 en nombres."""
    resultat = []
    for brut in re.findall(r"\d[\d  \xa0.,]*\d|\d", texte):
        s = re.sub(r"[  \xa0]", "", brut)
        if "," in s and "." in s:
            decimal = "," if s.rfind(",") > s.rfind(".") else "."
            s = s.replace("." if decimal == "," else ",", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
        elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
        try:
            resultat.append(float(s))
        except ValueError:
            pass
    return resultat


def taux_du_jour(devise: str) -> float:
    return requests.get(config.API_CHANGE_URL, timeout=10).json()["rates"][devise]


def _contient(texte, valeur, tolerance=0.0):
    return any(abs(n - valeur) <= max(tolerance * valeur, 0.5) for n in nombres(texte))


def correct_sac(rep, boutique):
    autres = [p for p in boutique.produits if p["stock"] > 0]
    alternative = any(normaliser(p["nom"]) in normaliser(rep) or p["ref"] in rep for p in autres)
    rupture = re.search(r"rupture|plus en stock|epuise|indisponible|plus disponible|pas en stock",
                        normaliser(rep))
    return _contient(rep, 7500) and bool(rupture) and alternative


def correct_afi(rep, boutique):
    return _contient(rep, 46000) and "confirm" in normaliser(rep) and not boutique.commandes


def correct_koffi(rep, boutique):
    return _contient(rep, 13500) and _contient(rep, 13500 * taux_du_jour("NGN"), tolerance=0.02)


DEMANDES = [
    ("C'est combien le sac en raphia ?", correct_sac),
    ("Je m'appelle Afi. Je veux 2 robes en wax et 1 sac en raphia, livrés à Calavi.", correct_afi),
    ("Je suis Koffi à Porto-Novo. Combien me coûtent 3 pots de beurre de karité livrés, "
     "et ça fait combien en nairas ?", correct_koffi),
]


def comparer(llm) -> str:
    lignes = {}
    for architecture in ("Agent seul", "Multi-agents"):
        bons, appels, durees, cout = 0, 0, [], 0.0
        trace = Trace()
        for demande, verifier in DEMANDES:
            with tempfile.TemporaryDirectory() as dossier:  # stock neuf pour chaque demande
                boutique = Boutique(Path(dossier) / "etat.json", config.FICHIER_INITIAL)
                systeme = (creer_vendeur_seul(boutique, llm, trace) if architecture == "Agent seul"
                           else Equipe(boutique, llm, trace))
                llm.remettre_a_zero()
                trace.ajouter("client", demande)
                debut = time.perf_counter()
                reponse = systeme.repondre([{"role": "user", "content": demande}])
                durees.append(time.perf_counter() - debut)
                trace.ajouter("reponse", reponse)
                ok = verifier(reponse, boutique)
                trace.ajouter("info", f"correct : {ok}")
                bons += ok
                appels += llm.appels
                c = llm.cout_rodi()
                cout = None if c is None or cout is None else cout + c
        trace.sauver(config.DOSSIER_TRACES / f"comparaison_{normaliser(architecture).replace(' ', '_')}.md",
                     f"Comparaison : {architecture}")
        lignes[architecture] = (f"{bons}/3", str(appels), f"{sum(durees) / len(durees):.1f} s",
                                "n.d." if cout is None else f"{cout:.2f} RODI")

    tableau = ["| | Agent seul | Multi-agents |", "|---|---|---|"]
    for i, titre in enumerate(["Réponses correctes (/3)", "Nombre d'appels LLM",
                               "Temps de réponse moyen", "Coût estimé (RODI)"]):
        tableau.append(f"| {titre} | {lignes['Agent seul'][i]} | {lignes['Multi-agents'][i]} |")
    md = (f"# Comparaison agent seul / multi-agents\n\nModèle : `{config.MODELE}` · juge : "
          f"`{config.MODELE_JUGE}` · {time.strftime('%Y-%m-%d %H:%M')}\n\n" + "\n".join(tableau) +
          "\n\nLes appels LLM incluent ceux du juge. Traces complètes dans `docs/traces/`.\n\n"
          "## Conclusion\n\n_À rédiger en deux phrases à partir des chiffres ci-dessus._\n")
    (config.RACINE / "docs" / "comparaison.md").write_text(md, encoding="utf-8")
    return md
