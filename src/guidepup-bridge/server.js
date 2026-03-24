import express from "express";
import bodyParser from "body-parser";
import pino from "pino";
import { voiceOver, nvda } from "@guidepup/guidepup";

const app = express();
const log = pino();
app.use(bodyParser.json());


const TOKEN = process.env.GUIDEPUP_BRIDGE_TOKEN || null;
app.use((req, res, next) => {
  if (!TOKEN) return next();
  const auth = req.header("Authorization") || "";
  if (auth === `Bearer ${TOKEN}`) return next();
  return res.status(401).json({ error: "Unauthorized" });
});


let sr = null;
let srType = 'voiceover'; // "voiceover" or "nvda"
let running = false;


function getSR(reader) {
  if (reader === "voiceover") return voiceOver;
  if (reader === "nvda") return nvda;
  throw new Error(`Unsupported reader: ${reader}`);
}

let commandQueue = Promise.resolve();
function enqueue(fn) {
  commandQueue = commandQueue.then(fn, fn);
  return commandQueue;
}

app.get("/health", (_req, res) => res.json({ ok: true, running, srType }));

app.post("/start", (req, res) => {
  const reader = (req.body?.reader || "").toLowerCase();
  enqueue(async () => {
    if (running && srType === reader) return;
    if (!reader) throw new Error("Missing 'reader' (voiceover|nvda)");
    sr = getSR(reader);
    await sr.start();
    srType = reader;
    running = true;
  })
    .then(() => res.json({ ok: true, srType }))
    .catch((e) => res.status(500).json({ error: e.message }));
});

app.post("/stop", (_req, res) => {
  enqueue(async () => {
    if (sr && running) {
      await sr.stop();
    }
    running = false;
    srType = null;
    sr = null;
  })
    .then(() => res.json({ ok: true }))
    .catch((e) => res.status(500).json({ error: e.message }));
});

app.post("/action", (req, res) => {
  const { name } = req.body || {};
  enqueue(async () => {
    if (!running || !sr) throw new Error("Screen reader not started");
    switch (name) {
      case "next":
        await sr.next();
        break;
      case "previous":
        await sr.previous?.();
        break;
      default:
        throw new Error(`Unsupported action: ${name}`);
    }
  })
    .then(() => res.json({ ok: true }))
    .catch((e) => res.status(500).json({ error: e.message }));
});


app.post("/perform", (req, res) => {
  const { commandKey } = req.body || {};
  enqueue(async () => {
    if (!running || !sr) throw new Error("Screen reader not started");
    const cmd = sr.keyboardCommands?.[commandKey];
    if (!cmd) throw new Error(`Unknown keyboard command: ${commandKey}`);
    await sr.perform(cmd);
  })
    .then(() => res.json({ ok: true }))
    .catch((e) => res.status(500).json({ error: e.message }));
});


app.get("/spoken-phrases", (_req, res) => {
  enqueue(async () => {
    if (!running || !sr) throw new Error("Screen reader not started");
    const log = await sr.spokenPhraseLog();
    res.json({ ok: true, log });
  }).catch((e) => res.status(500).json({ error: e.message }));
});

app.get("/last-spoken-phrase", (_req, res) => {
  enqueue(async () => {
    if (!running || !sr) throw new Error("Screen reader not started");
    const phrase = await sr.lastSpokenPhrase();
    res.json({ ok: true, phrase });
  }).catch((e) => res.status(500).json({ error: e.message }));
});

app.get("/item-text", (_req, res) => {
  enqueue(async () => {
    if (!running || !sr) throw new Error("Screen reader not started");
    const text = await sr.itemText();
    res.json({ ok: true, text });
  }).catch((e) => res.status(500).json({ error: e.message }));
});



const port = process.env.PORT || 8787;
app.listen(port, () => log.info(`Guidepup bridge listening on :${port}`));
// CLI: node server.js