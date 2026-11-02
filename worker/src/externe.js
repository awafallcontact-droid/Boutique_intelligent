// Appels sortants : LLM RodiumAi (compatible OpenAI) et Green API.

export function creerLLM(env, fetchFn) {
  const base = (env.RODIUM_BASE_URL ?? "https://api.rodiumai.io/v1").replace(/\/$/, "");
  return {
    async chat(messages, outils, modele) {
      const corps = { model: modele ?? env.MODELE, messages };
      if (outils?.length) Object.assign(corps, { tools: outils, tool_choice: "auto" });
      const r = await fetchFn(`${base}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${env.RODIUM_API_KEY}` },
        body: JSON.stringify(corps),
      });
      if (!r.ok) throw new Error(`RodiumAi ${r.status} : ${(await r.text()).slice(0, 300)}`);
      const message = (await r.json()).choices[0].message;
      return { content: message.content, tool_calls: message.tool_calls };
    },
  };
}

// Méthode sendMessage : POST {apiUrl}/waInstance{idInstance}/sendMessage/{apiTokenInstance}
export function creerEnvoi(env, fetchFn) {
  return async (chatId, message) => {
    const url = `${env.GREEN_API_URL}/waInstance${env.GREEN_ID_INSTANCE}/sendMessage/${env.GREEN_API_TOKEN}`;
    const r = await fetchFn(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chatId, message }),
    });
    console.log(JSON.stringify({ type: "envoi", chatId, statut: r.status }));
    if (!r.ok) console.error(JSON.stringify({ type: "erreur_envoi", chatId, statut: r.status }));
  };
}
