"""La boucle d'agent avec un faux LLM : enchaînement, max_steps, validation, évaluation."""
import json

from boutique.agent import REPONSE_SECOURS, Agent
from boutique.equipe import Equipe
from boutique.evaluation import Verdict
from boutique.outils import creer_outils
from boutique.trace import Trace

from .conftest import FauxLLM, appel, texte


def agent(boutique, llm, **options):
    return Agent("Vendeur", "instructions", creer_outils(boutique), llm,
                 trace=Trace(afficher=False), **options)


def resultats_outils(llm):
    return [json.loads(m["content"]) for m in llm.recus[-1] if m["role"] == "tool"]


def test_enchaine_deux_outils_dans_l_ordre(boutique, faux_change):
    llm = FauxLLM([appel("chercher_produits", mot_cle="pagne"),
                   appel("convertir_devise", montant_fcfa=12000, devise="EUR"),
                   texte("Le pagne wax coûte 12 000 FCFA, soit 18 EUR.")])
    a = agent(boutique, llm)
    assert a.repondre([{"role": "user", "content": "pagnes en euros ?"}]) == "Le pagne wax coûte 12 000 FCFA, soit 18 EUR."
    outils = [l.split("(")[0].split()[-1] for l in a.trace.lignes if l.startswith("OUTIL")]
    assert outils == ["chercher_produits", "convertir_devise"]


def test_max_steps(boutique):
    llm = FauxLLM([appel("verifier_stock", ref="P01")] * 3)
    assert agent(boutique, llm, max_steps=3).repondre([]) == REPONSE_SECOURS
    assert llm.appels == 3


def test_commande_bloquee_sans_accord_du_client(boutique):
    llm = FauxLLM([appel("creer_commande", client="Afi", zone="Calavi",
                         articles=[{"ref": "P05", "quantite": 2}]), texte("ok")])
    agent(boutique, llm, validateur=lambda a: True).repondre([], client_a_confirme=False)
    assert "refus" in resultats_outils(llm)[0] and boutique.commandes == []


def test_refus_d_afi_renvoye_comme_observation_puis_acceptation(boutique):
    commande = appel("creer_commande", client="Afi", zone="Calavi", articles=[{"ref": "P05", "quantite": 2}])
    decisions = iter([False, True])
    llm = FauxLLM([commande, texte("Afi n'a pas validé."), commande, texte("Commande n°1 validée.")])
    a = agent(boutique, llm, validateur=lambda args: next(decisions))
    a.repondre([], client_a_confirme=True)
    assert "refus" in resultats_outils(llm)[0] and boutique.commandes == []
    a.repondre([], client_a_confirme=True)
    assert boutique.commandes[0]["total"] == 46000 and boutique.produit("P05")["stock"] == 3


def test_evaluation_pas_encore_puis_ok(boutique):
    llm = FauxLLM([texte("brouillon"), texte("version corrigée")])
    verdicts = iter([Verdict(False, "Total faux."), Verdict(True)])
    a = agent(boutique, llm, evaluateur=lambda *args: next(verdicts))
    assert a.repondre([{"role": "user", "content": "?"}]) == "version corrigée"
    assert "Total faux." in llm.recus[-1][-1]["content"]  # la critique est ajoutée au contexte


def test_evaluation_toujours_negative_donne_la_reponse_de_secours(boutique):
    llm = FauxLLM([texte("faux")] * 3)
    a = agent(boutique, llm, max_reprises=2, evaluateur=lambda *args: Verdict(False, "non"))
    assert a.repondre([{"role": "user", "content": "?"}]) == REPONSE_SECOURS


def test_equipe_le_gerant_ne_voit_que_le_resume(boutique, monkeypatch):
    monkeypatch.setattr("boutique.equipe.creer_evaluateur", lambda *a, **k: lambda *x: Verdict(True))
    llm = FauxLLM([
        appel("demander_au_vendeur", mission="Prix et stock du sac en raphia ?"),  # Gérant
        appel("verifier_stock", ref="P03"),                                        # Vendeur
        texte("P03 Sac en raphia : 7 500 FCFA, rupture."),                         # Vendeur -> résumé
        texte("Le sac en raphia (7 500 FCFA) est en rupture."),                    # Gérant
    ])
    reponse = Equipe(boutique, llm, Trace(afficher=False)).repondre([{"role": "user", "content": "sac ?"}])
    assert reponse == "Le sac en raphia (7 500 FCFA) est en rupture."
    contexte_gerant = json.dumps(llm.recus[-1], ensure_ascii=False)
    assert "alternatives_en_stock" not in contexte_gerant  # pas de résultat d'outil brut
    assert "rupture" in contexte_gerant  # seulement le résumé
