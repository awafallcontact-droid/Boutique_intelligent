"""Client LLM pour l'API RodiumAi (compatible OpenAI : POST /v1/chat/completions).

Compte aussi les appels et les tokens, pour le tableau de comparaison (palier 2b).
Le coût en RODI est calculé avec les tarifs publiés par GET /v1/models."""
import requests

from . import config


class ErreurLLM(RuntimeError):
    pass


class ClientRodium:
    def __init__(self, api_key=config.RODIUM_API_KEY, modele=config.MODELE,
                 base_url=config.RODIUM_BASE_URL, timeout=90):
        if not api_key:
            raise ErreurLLM("RODIUM_API_KEY manquante : copiez .env.example en .env et ajoutez votre clé.")
        self.api_key, self.modele, self.base_url, self.timeout = api_key, modele, base_url.rstrip("/"), timeout
        self._tarifs = None
        self.remettre_a_zero()

    def remettre_a_zero(self):
        self.appels = 0
        self.tokens = {}  # modele -> [entree, sortie]

    def chat(self, messages: list[dict], outils: list[dict] | None = None, modele: str | None = None) -> dict:
        modele = modele or self.modele
        corps = {"model": modele, "messages": messages}
        if outils:
            corps["tools"] = outils
            corps["tool_choice"] = "auto"
        try:
            r = requests.post(f"{self.base_url}/chat/completions", json=corps, timeout=self.timeout,
                              headers={"Authorization": f"Bearer {self.api_key}"})
        except requests.RequestException as e:
            raise ErreurLLM(f"RodiumAi injoignable : {e}") from e
        if r.status_code >= 400:
            raise ErreurLLM(f"RodiumAi a répondu {r.status_code} : {r.text[:300]}")
        donnees = r.json()
        self.appels += 1
        usage = donnees.get("usage") or {}
        compteur = self.tokens.setdefault(modele, [0, 0])
        compteur[0] += usage.get("prompt_tokens", 0)
        compteur[1] += usage.get("completion_tokens", 0)
        message = donnees["choices"][0]["message"]
        return {"content": message.get("content"), "tool_calls": message.get("tool_calls")}

    def cout_rodi(self) -> float | None:
        """Coût estimé en RODI d'après les tarifs par million de tokens de /v1/models."""
        if self._tarifs is None:
            try:
                liste = requests.get(f"{self.base_url}/models", timeout=20).json()["data"]
                self._tarifs = {m["id"]: m.get("rodiumai_pricing") or {} for m in liste}
            except (requests.RequestException, ValueError, KeyError):
                return None
        total = 0.0
        for modele, (entree, sortie) in self.tokens.items():
            t = self._tarifs.get(modele, {})
            if t.get("input_per_1m") is None or t.get("output_per_1m") is None:
                return None  # ex. routeurs rodium/* : pas de tarif fixe publié
            total += entree / 1e6 * t["input_per_1m"] + sortie / 1e6 * t["output_per_1m"]
        return round(total, 2)
