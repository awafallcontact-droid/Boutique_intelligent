"""Mémoire persistante : stock, zones et commandes dans un fichier JSON (palier 2a)."""
import json
import os
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


def normaliser(texte: str) -> str:
    """Minuscules, sans accents ni tirets : « Fidjrossè » == « fidjrosse »."""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode()
    return " ".join(t.lower().replace("-", " ").split())


class Boutique:
    """Le fichier JSON est la seule source de vérité : on le relit avant chaque écriture."""

    def __init__(self, fichier_etat, fichier_initial):
        self.fichier = Path(fichier_etat)
        self.fichier_initial = Path(fichier_initial)
        if not self.fichier.exists():
            self.reinitialiser()
        self._lire()

    def reinitialiser(self):
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.fichier_initial, self.fichier)
        self._lire()

    def _lire(self):
        self.etat = json.loads(self.fichier.read_text(encoding="utf-8"))

    def _ecrire(self):
        # Écriture atomique : un crash au milieu ne corrompt pas le fichier.
        tmp = self.fichier.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.etat, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.fichier)

    # --- lecture -------------------------------------------------------------

    @property
    def produits(self) -> list[dict]:
        return self.etat["produits"]

    @property
    def commandes(self) -> list[dict]:
        return self.etat["commandes"]

    @property
    def delai(self) -> str:
        return self.etat["delai"]

    def produit(self, ref: str) -> dict | None:
        ref = str(ref).strip().upper()
        return next((p for p in self.produits if p["ref"] == ref), None)

    def zones(self) -> list[str]:
        return list(self.etat["zones"])

    def zone(self, nom: str) -> tuple[str, int] | None:
        """Renvoie (nom officiel, frais) ou None si la zone n'est pas desservie."""
        cible = normaliser(nom)
        for officiel, frais in self.etat["zones"].items():
            if normaliser(officiel) == cible:
                return officiel, frais
        return None

    def devis(self, zone: str, articles: list[dict]) -> dict:
        """Calcul en code du total = articles + livraison. Sert à l'outil ET à l'évaluation."""
        z = self.zone(zone)
        if z is None:
            return {"erreur": "zone non desservie", "zones_desservies": self.zones()}
        if not articles:
            return {"erreur": "aucun article"}
        lignes = []
        for a in articles:
            p = self.produit(a.get("ref", ""))
            if p is None:
                return {"erreur": f"référence inconnue : {a.get('ref')}"}
            q = int(a.get("quantite", 0))
            if q < 1:
                return {"erreur": f"quantité invalide pour {p['nom']}"}
            if q > p["stock"]:
                return {"erreur": f"stock insuffisant pour {p['nom']}", "stock_disponible": p["stock"]}
            lignes.append({"ref": p["ref"], "nom": p["nom"], "quantite": q,
                           "prix_unitaire": p["prix"], "montant": q * p["prix"]})
        sous_total = sum(l["montant"] for l in lignes)
        return {"lignes": lignes, "zone": z[0], "frais_livraison": z[1],
                "sous_total": sous_total, "total": sous_total + z[1], "delai": self.delai}

    # --- écriture ------------------------------------------------------------

    def enregistrer_commande(self, client: str, devis: dict) -> dict:
        self._lire()
        for ligne in devis["lignes"]:
            p = self.produit(ligne["ref"])
            if ligne["quantite"] > p["stock"]:  # le stock a pu bouger entre-temps
                raise ValueError(f"stock insuffisant pour {p['nom']}")
        for ligne in devis["lignes"]:
            self.produit(ligne["ref"])["stock"] -= ligne["quantite"]
        commande = {
            "numero": self.etat["prochain_numero"],
            "client": client,
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **{k: devis[k] for k in ("lignes", "zone", "frais_livraison", "total")},
        }
        self.etat["commandes"].append(commande)
        self.etat["prochain_numero"] += 1
        self._ecrire()
        return commande
