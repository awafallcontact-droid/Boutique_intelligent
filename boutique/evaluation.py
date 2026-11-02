"""Évaluation avant la réponse finale (palier 2a), à deux niveaux :
1. une règle en code : le total annoncé == articles + livraison, recalculé depuis les données ;
2. un LLM juge avec des critères écrits.
Si l'un dit « pas encore », la critique repart dans le contexte et l'agent recommence."""
import json
import re
from dataclasses import dataclass

from .donnees import Boutique
from .trace import Trace

CRITERES_JUGE = """\
1. Aucun chiffre inventé : chaque prix, stock, frais, délai, taux ou montant converti de la réponse
   figure dans les observations des outils, ou se calcule directement à partir d'elles
   (quantité x prix, somme, total). Les quantités demandées par le client et les numéros de
   commande sont permis. Si aucune observation n'est fournie, la réponse ne doit contenir aucun prix.
2. Si une observation indique une rupture (stock 0, « rupture » ou « stock insuffisant »), la réponse
   le dit clairement et propose une alternative tirée des observations.
3. La réponse fait moins de 80 mots."""

RE_TOTAL = re.compile(r"total[^0-9\n]*?(\d[\d .]*\d|\d)\s*f\s?cfa", re.IGNORECASE)
RE_LIGNE = re.compile(r"(\d+)\s*[x×]\s*[^\n(]*\((P\d{2})\)", re.IGNORECASE)
RE_LIVRAISON = re.compile(r"livraison\s+(?:à\s+|a\s+)?([^\n:(]+?)\s*:", re.IGNORECASE)

FORMAT_RECAP = ("Écris chaque article sous la forme « - <quantité> x <nom> (<réf>) : <montant> FCFA », puis "
                "« Livraison <zone> : <frais> FCFA », puis « Total : <total> FCFA ».")


@dataclass
class Verdict:
    ok: bool
    critique: str = ""
    source: str = ""


def _nettoyer(texte: str) -> str:
    """Enlève le gras WhatsApp et les espaces insécables (46 000 écrit avec U+202F)."""
    return re.sub(r"[*_~]", "", texte.replace(" ", " ").replace("\xa0", " "))


def verifier_total(texte: str, boutique: Boutique) -> Verdict:
    t = _nettoyer(texte)
    totaux = [m for m in RE_TOTAL.finditer(t) if "sous" not in t[max(0, m.start() - 5):m.start()].lower()]
    if not totaux:
        return Verdict(True, source="règle")  # pas de total annoncé : rien à vérifier
    annonce = int(re.sub(r"\D", "", totaux[-1].group(1)))
    lignes = RE_LIGNE.findall(t)
    zone = RE_LIVRAISON.search(t)
    if not lignes or not zone:
        return Verdict(False, "Tu annonces un total sans récapitulatif vérifiable. " + FORMAT_RECAP, "règle")
    devis = boutique.devis(zone.group(1).strip(),
                           [{"ref": ref.upper(), "quantite": int(q)} for q, ref in lignes])
    if "erreur" in devis:
        return Verdict(False, f"Récapitulatif impossible à honorer : {devis['erreur']}. "
                              "Retire l'article concerné ou corrige la zone, puis recalcule.", "règle")
    if annonce != devis["total"]:
        return Verdict(False, f"Total faux : tu annonces {annonce} FCFA, mais articles + livraison = "
                              f"{devis['total']} FCFA.", "règle")
    return Verdict(True, source="règle")


def juger_avec_llm(llm, modele: str, texte: str, observations: list[dict], demande: str) -> Verdict:
    consigne = [
        {"role": "system", "content":
            "Tu es l'évaluateur qualité d'un vendeur WhatsApp. Tu vérifies une réponse AVANT son envoi. "
            "Critères :\n" + CRITERES_JUGE +
            '\nRéponds uniquement en JSON : {"verdict": "ok" | "pas encore", "critique": "..."}. '
            "La critique dit précisément quoi corriger (vide si ok)."},
        {"role": "user", "content":
            f"Demande du client :\n{demande}\n\nObservations des outils (JSON) :\n"
            f"{json.dumps(observations, ensure_ascii=False)}\n\nRéponse proposée :\n{texte}\n\n"
            f"Nombre de mots (compté par le code) : {len(texte.split())}"},
    ]
    brut = llm.chat(consigne, None, modele=modele).get("content") or ""
    m = re.search(r"\{.*\}", brut, re.DOTALL)
    try:
        avis = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        avis = {}
    if avis.get("verdict") not in ("ok", "pas encore"):
        # Un juge illisible ne laisse rien passer (on préfère la réponse de secours).
        return Verdict(False, "Évaluation illisible, reformule ta réponse en respectant les règles.", "juge")
    return Verdict(avis["verdict"] == "ok", avis.get("critique", ""), "juge")


def creer_evaluateur(boutique: Boutique, llm, modele_juge: str, trace: Trace, agent: str = ""):
    def evaluer(texte: str, observations: list[dict], historique: list[dict]) -> Verdict:
        demande = next((m["content"] for m in reversed(historique) if m["role"] == "user"), "")
        verdict = verifier_total(texte, boutique)  # la règle en code passe d'abord : gratuite et sûre
        if verdict.ok:
            verdict = juger_avec_llm(llm, modele_juge, texte, observations, demande)
        trace.ajouter("eval", f"{verdict.source} : {'ok' if verdict.ok else 'pas encore'}"
                              f"{' : ' + verdict.critique if verdict.critique else ''}", agent)
        return verdict
    return evaluer
