"""Outils de test hors ligne : boutique temporaire et faux LLM scripté (aucun appel réseau)."""
import json
from types import SimpleNamespace

import pytest

from boutique import config
from boutique.donnees import Boutique


@pytest.fixture
def boutique(tmp_path):
    return Boutique(tmp_path / "etat.json", config.FICHIER_INITIAL)


def appel(nom, **arguments):
    return {"tool_calls": [{"id": f"id_{nom}", "type": "function",
                            "function": {"name": nom, "arguments": json.dumps(arguments)}}]}


def texte(contenu):
    return {"content": contenu}


class FauxLLM:
    """Rejoue une liste de réponses dans l'ordre et garde les messages reçus."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.recus = []
        self.appels = 0

    def chat(self, messages, outils=None, modele=None):
        self.recus.append(messages)
        self.appels += 1
        return self.reponses.pop(0)


@pytest.fixture
def faux_change(monkeypatch):
    """Remplace l'API de taux par une réponse fixe (taux fictifs, pour les tests uniquement)."""
    donnees = {"result": "success", "time_last_update_utc": "test",
               "rates": {"XOF": 1, "EUR": 0.0015, "NGN": 2.3}}
    reponse = SimpleNamespace(json=lambda: donnees, raise_for_status=lambda: None)
    monkeypatch.setattr("boutique.outils.requests.get", lambda *a, **k: reponse)
