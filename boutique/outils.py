"""Les 5 outils du palier 1 : nom en verbe_objet, description qui dit QUAND s'en servir,
message d'erreur imposé par l'énoncé. Chaque outil renvoie un dict sérialisable en JSON."""
from dataclasses import dataclass
from typing import Callable

import requests

from . import config
from .donnees import Boutique, normaliser

MOTS_VIDES = {"de", "des", "du", "en", "le", "la", "les", "un", "une", "pour", "et", "a"}


@dataclass
class Outil:
    nom: str
    description: str
    parametres: dict
    fonction: Callable[..., dict]
    irreversible: bool = False  # déclenche la validation humaine (palier 2a)

    def schema(self) -> dict:
        return {"type": "function",
                "function": {"name": self.nom, "description": self.description,
                             "parameters": self.parametres}}


def _mots(texte: str) -> list[str]:
    mots = [m for m in normaliser(texte).split() if m not in MOTS_VIDES and len(m) >= 3]
    return [m[:-1] if m.endswith("s") and len(m) > 3 else m for m in mots]  # pagnes -> pagne


def creer_outils(boutique: Boutique, url_change: str = config.API_CHANGE_URL) -> dict[str, Outil]:

    def chercher_produits(mot_cle: str) -> dict:
        if normaliser(mot_cle) in {"tout", "catalogue", "produits"}:
            trouves = boutique.produits
        else:
            requete = _mots(mot_cle)
            trouves = [p for p in boutique.produits
                       if any(q == m or (len(q) >= 4 and m.startswith(q))
                              for q in requete for m in _mots(p["nom"]))]
        if not trouves:
            return {"erreur": f"aucun produit pour {mot_cle}"}
        return {"produits": [{"ref": p["ref"], "nom": p["nom"], "prix_fcfa": p["prix"]} for p in trouves]}

    def verifier_stock(ref: str) -> dict:
        p = boutique.produit(ref)
        if p is None:
            return {"erreur": "référence inconnue", "ref": ref}
        resultat = {"ref": p["ref"], "nom": p["nom"], "prix_fcfa": p["prix"], "stock": p["stock"],
                    "statut": "disponible" if p["stock"] > 0 else "rupture"}
        if p["stock"] == 0:
            resultat["alternatives_en_stock"] = [
                {"ref": a["ref"], "nom": a["nom"], "prix_fcfa": a["prix"], "stock": a["stock"]}
                for a in boutique.produits if a["stock"] > 0]
        return resultat

    def frais_livraison(zone: str) -> dict:
        z = boutique.zone(zone)
        if z is None:
            return {"erreur": "zone non desservie", "zones_desservies": boutique.zones()}
        return {"zone": z[0], "frais_fcfa": z[1], "delai": boutique.delai}

    def convertir_devise(montant_fcfa: float, devise: str) -> dict:
        # Règle 5 : taux réel, récupéré au moment de la question (pas de cache).
        try:
            r = requests.get(url_change, timeout=10)
            r.raise_for_status()
            donnees = r.json()
        except (requests.RequestException, ValueError):
            return {"erreur": "service de change indisponible, réessayer plus tard"}
        code = str(devise).strip().upper()
        taux = donnees.get("rates", {}).get(code)
        if taux is None or code == "XOF":
            return {"erreur": "devise non prise en charge", "devise": devise}
        return {"montant_fcfa": montant_fcfa, "devise": code,
                "montant_converti": round(montant_fcfa * taux, 2), "taux_1_fcfa": taux,
                "date_du_taux": donnees.get("time_last_update_utc"), "source": "open.er-api.com"}

    def creer_commande(client: str, zone: str, articles: list[dict]) -> dict:
        devis = boutique.devis(zone, articles)
        if "erreur" in devis:
            return devis
        try:
            commande = boutique.enregistrer_commande(client, devis)
        except ValueError as e:
            return {"erreur": str(e)}
        return {"statut": "enregistrée", **commande}

    outils = [
        Outil("chercher_produits",
              "Trouve des produits du catalogue par mot-clé (ex. 'pagne', 'robe', 'karité') et donne "
              "leur référence et leur prix en FCFA. À utiliser dès que le client parle d'un produit, "
              "avant toute autre action. Mot-clé 'catalogue' pour tout lister.",
              {"type": "object", "properties": {"mot_cle": {"type": "string"}},
               "required": ["mot_cle"]},
              chercher_produits),
        Outil("verifier_stock",
              "Donne le stock d'une référence (ex. 'P05'). À utiliser AVANT de dire qu'un produit est "
              "disponible ou d'accepter une quantité. En cas de rupture, renvoie les alternatives en stock.",
              {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]},
              verifier_stock),
        Outil("frais_livraison",
              "Donne les frais (FCFA) et le délai de livraison pour une zone. À utiliser dès que le "
              "client indique où livrer, et avant d'annoncer un total.",
              {"type": "object", "properties": {"zone": {"type": "string"}}, "required": ["zone"]},
              frais_livraison),
        Outil("convertir_devise",
              "Convertit un montant en FCFA vers une devise (code ISO : EUR, USD, NGN, GBP, CAD...) au "
              "taux réel du moment. À utiliser dès que le client veut un prix dans sa devise, avec un "
              "montant FCFA obtenu d'un autre outil.",
              {"type": "object",
               "properties": {"montant_fcfa": {"type": "number"},
                              "devise": {"type": "string", "description": "Code ISO 4217, ex. EUR"}},
               "required": ["montant_fcfa", "devise"]},
              convertir_devise),
        Outil("creer_commande",
              "Enregistre une commande et décrémente le stock. ACTION IRRÉVERSIBLE : à utiliser "
              "uniquement après que le client a explicitement accepté le récapitulatif (articles, "
              "livraison, total).",
              {"type": "object",
               "properties": {
                   "client": {"type": "string", "description": "Nom du client"},
                   "zone": {"type": "string"},
                   "articles": {"type": "array", "items": {
                       "type": "object",
                       "properties": {"ref": {"type": "string"}, "quantite": {"type": "integer"}},
                       "required": ["ref", "quantite"]}}},
               "required": ["client", "zone", "articles"]},
              creer_commande, irreversible=True),
    ]
    return {o.nom: o for o in outils}
