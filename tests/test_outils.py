from boutique.outils import creer_outils


def test_chercher_produits_trouve_les_pagnes(boutique):
    r = creer_outils(boutique)["chercher_produits"].fonction(mot_cle="pagnes")
    assert r == {"produits": [{"ref": "P01", "nom": "Pagne wax 6 yards", "prix_fcfa": 12000}]}


def test_chercher_produits_erreur(boutique):
    r = creer_outils(boutique)["chercher_produits"].fonction(mot_cle="téléphone")
    assert r == {"erreur": "aucun produit pour téléphone"}


def test_verifier_stock_rupture_propose_des_alternatives(boutique):
    r = creer_outils(boutique)["verifier_stock"].fonction(ref="p03")
    assert r["statut"] == "rupture" and r["prix_fcfa"] == 7500
    assert "P03" not in [a["ref"] for a in r["alternatives_en_stock"]]


def test_verifier_stock_reference_inconnue(boutique):
    assert creer_outils(boutique)["verifier_stock"].fonction(ref="P99")["erreur"] == "référence inconnue"


def test_frais_livraison(boutique):
    f = creer_outils(boutique)["frais_livraison"].fonction
    assert f(zone="fidjrosse") == {"zone": "Fidjrossè", "frais_fcfa": 1500, "delai": "24 à 48 h"}
    lome = f(zone="Lomé")
    assert lome["erreur"] == "zone non desservie" and "Calavi" in lome["zones_desservies"]


def test_convertir_devise(boutique, faux_change):
    f = creer_outils(boutique)["convertir_devise"].fonction
    assert f(montant_fcfa=12000, devise="eur")["montant_converti"] == 18.0
    assert f(montant_fcfa=12000, devise="ZZZ")["erreur"] == "devise non prise en charge"


def test_creer_commande_persiste_et_decremente(boutique, tmp_path):
    f = creer_outils(boutique)["creer_commande"].fonction
    r = f(client="Afi", zone="Calavi", articles=[{"ref": "P05", "quantite": 2}])
    assert r["statut"] == "enregistrée" and r["total"] == 46000 and r["numero"] == 1
    relue = type(boutique)(tmp_path / "etat.json", boutique.fichier_initial)  # relit le fichier
    assert relue.produit("P05")["stock"] == 3 and len(relue.commandes) == 1


def test_creer_commande_stock_insuffisant(boutique):
    f = creer_outils(boutique)["creer_commande"].fonction
    r = f(client="Afi", zone="Calavi", articles=[{"ref": "P03", "quantite": 1}])
    assert r["erreur"] == "stock insuffisant pour Sac en raphia"
    assert boutique.commandes == []
