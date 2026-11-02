"""Règle 4 : accord explicite du client ET validation d'Afi."""
import re

from .donnees import Boutique, normaliser

RE_OUI = re.compile(r"\b(oui|je confirme|confirme|confirmer|d accord|ok|je valide|valide|c est bon)\b")
RE_NON = re.compile(r"\b(non|pas d accord|annule)\b")


def est_confirmation(texte: str) -> bool:
    """Le client a-t-il dit oui dans son dernier message ? Décidé par le code, pas par le LLM."""
    t = normaliser(texte).replace("'", " ").replace("’", " ")
    return bool(RE_OUI.search(t)) and not RE_NON.search(t)


def validateur_console(boutique: Boutique):
    """Palier 2a : le programme demande « Valider la commande ? [o/N] » à Afi dans le terminal."""
    def valider(arguments: dict) -> bool:
        devis = boutique.devis(arguments.get("zone", ""), arguments.get("articles", []))
        if "erreur" in devis:
            return True  # l'outil renverra lui-même l'erreur, sans rien enregistrer
        print("\n----- Demande de validation pour Afi -----")
        print(f"Client : {arguments.get('client')}")
        for l in devis["lignes"]:
            print(f"  {l['quantite']} x {l['nom']} ({l['ref']}) : {l['montant']} FCFA")
        print(f"  Livraison {devis['zone']} : {devis['frais_livraison']} FCFA")
        print(f"  Total : {devis['total']} FCFA")
        return input("Valider la commande ? [o/N] ").strip().lower() in ("o", "oui")
    return valider
