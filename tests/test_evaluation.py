from boutique.comparaison import nombres
from boutique.evaluation import verifier_total
from boutique.validation import est_confirmation

RECAP_AFI = """Bonjour Afi ! Le sac en raphia est en rupture 😔
- 2 x Robe en wax (P05) : 44 000 FCFA
Livraison Calavi : 2 000 FCFA
*Total : 46 000 FCFA*
Vous confirmez ?"""


def test_total_juste(boutique):
    assert verifier_total(RECAP_AFI, boutique).ok


def test_total_faux(boutique):
    v = verifier_total(RECAP_AFI.replace("46 000", "48 000"), boutique)
    assert not v.ok and "46000" in v.critique


def test_article_en_rupture_dans_le_total(boutique):
    texte = RECAP_AFI.replace("Livraison", "- 1 x Sac en raphia (P03) : 7 500 FCFA\nLivraison")
    assert not verifier_total(texte, boutique).ok


def test_injection_prix_a_1000(boutique):
    texte = "- 1 x Robe en wax (P05) : 1 000 FCFA\nLivraison Cotonou : 1 000 FCFA\nTotal : 2 000 FCFA"
    assert not verifier_total(texte, boutique).ok


def test_total_sans_recapitulatif(boutique):
    assert not verifier_total("Ça vous fera un total de 46 000 FCFA.", boutique).ok


def test_pas_de_total_rien_a_verifier(boutique):
    assert verifier_total("Le pagne wax coûte 12 000 FCFA.", boutique).ok


def test_confirmation():
    assert est_confirmation("Oui je confirme")
    assert est_confirmation("d'accord")
    assert not est_confirmation("Je veux 2 robes")
    assert not est_confirmation("non, pas d'accord")


def test_nombres():
    assert nombres("46 000 FCFA, soit 30 869,80 NGN ou 46.000") == [46000, 30869.8, 46000]
