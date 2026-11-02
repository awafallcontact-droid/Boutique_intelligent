"""La boucle d'agent : penser -> agir -> observer -> évaluer.

L'agent ne s'arrête pas quand il croit avoir fini : il s'arrête quand le code a vérifié
(évaluateur), ou quand il atteint max_steps."""
import json
from typing import Callable

from .outils import Outil
from .trace import Trace

REPONSE_SECOURS = ("Merci pour votre message ! Je préfère vérifier avec Afi avant de vous répondre "
                   "précisément. Elle revient vers vous très vite.")

REFUS_SANS_ACCORD_CLIENT = {
    "refus": "Le client n'a pas encore donné son accord explicite. Présente le récapitulatif "
             "(articles, livraison, total) et demande-lui de confirmer. Rien n'a été enregistré."}

REFUS_AFI = {
    "refus": "Afi n'a pas validé cette commande. Rien n'a été enregistré. Préviens le client "
             "poliment, sans inventer de raison."}


class Agent:
    def __init__(self, nom: str, instructions: str, outils: dict[str, Outil], llm,
                 max_steps: int = 8, evaluateur: Callable | None = None,
                 validateur: Callable[[dict], bool] | None = None,
                 trace: Trace | None = None, max_reprises: int = 2):
        self.nom, self.instructions, self.outils, self.llm = nom, instructions, outils, llm
        self.max_steps, self.max_reprises = max_steps, max_reprises
        self.evaluateur, self.validateur = evaluateur, validateur
        self.trace = trace or Trace()

    def repondre(self, historique: list[dict], client_a_confirme: bool = False) -> str:
        """historique : messages {role: user|assistant, content} de la conversation."""
        messages = [{"role": "system", "content": self.instructions}, *historique]
        schemas = [o.schema() for o in self.outils.values()] or None
        observations: list[dict] = []
        reprises = 0

        for etape in range(1, self.max_steps + 1):
            reponse = self.llm.chat(messages, schemas)
            appels = reponse.get("tool_calls") or []

            if appels:  # agir puis observer
                messages.append({"role": "assistant", "content": reponse.get("content") or "",
                                 "tool_calls": appels})
                for appel in appels:
                    nom = appel["function"]["name"]
                    arguments = _lire_arguments(appel["function"].get("arguments"))
                    resultat = self._executer(nom, arguments, client_a_confirme)
                    self.trace.outil(self.nom, etape, nom, arguments, resultat)
                    observations.append({"outil": nom, "arguments": arguments, "resultat": resultat})
                    messages.append({"role": "tool", "tool_call_id": appel["id"],
                                     "content": json.dumps(resultat, ensure_ascii=False)})
                continue

            texte = (reponse.get("content") or "").strip()
            if self.evaluateur is None:
                return texte

            verdict = self.evaluateur(texte, observations, historique)  # évaluer
            if verdict.ok:
                return texte
            if reprises >= self.max_reprises:
                self.trace.ajouter("limite", "évaluation toujours négative : réponse de secours", self.nom)
                return REPONSE_SECOURS
            reprises += 1
            messages.append({"role": "assistant", "content": texte})
            messages.append({"role": "user", "content":
                             f"[Évaluation interne, pas encore] {verdict.critique} "
                             "Réécris ta réponse au client en corrigeant ce point."})

        self.trace.ajouter("limite", f"max_steps={self.max_steps} atteint : réponse de secours", self.nom)
        return REPONSE_SECOURS

    def _executer(self, nom: str, arguments: dict, client_a_confirme: bool) -> dict:
        outil = self.outils.get(nom)
        if outil is None:
            return {"erreur": f"outil inconnu : {nom}"}
        if outil.irreversible:
            if not client_a_confirme:
                return REFUS_SANS_ACCORD_CLIENT
            if self.validateur is not None:
                accord = self.validateur(arguments)
                self.trace.ajouter("validation", "validée" if accord else "refusée", self.nom)
                if not accord:
                    return REFUS_AFI
        try:
            return outil.fonction(**arguments)
        except TypeError as e:  # arguments mal formés par le LLM : on le lui dit
            return {"erreur": f"arguments invalides pour {nom} : {e}"}


def _lire_arguments(brut) -> dict:
    if isinstance(brut, dict):
        return brut
    try:
        return json.loads(brut or "{}")
    except json.JSONDecodeError:
        return {}
