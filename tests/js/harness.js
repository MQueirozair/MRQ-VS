// Harness: extrai o <script> do index.html, monta o DOM mínimo e executa o
// Studio de verdade em Node — mesma lógica do navegador, sem servidor.
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const {Document, AudioEl} = require("./minidom");

const HTML = path.resolve(__dirname, "..", "..", "src", "mrqvs", "web", "index.html");

function extrairScript(html) {
  const m = /<script[^>]*>([\s\S]*?)<\/script>/.exec(html);
  if (!m) throw new Error("index.html sem bloco <script>");
  return m[1];
}

/** AudioContext falso com relógio controlável. */
function criarCtx() {
  const ctx = {
    _agora: 1.0,
    state: "running",
    destination: {connect() {}},
    sampleRate: 44100,
    get currentTime() { return this._agora; },
    avancar(s) { this._agora += s; },
    resume() { this.state = "running"; return Promise.resolve(); },
    createGain() {
      return {
        gain: {
          value: 1,
          setValueAtTime() {},
          setTargetAtTime(v) { this.value = v; },
          exponentialRampToValueAtTime() {},
        },
        connect() {}, disconnect() {},
      };
    },
    createStereoPanner() {
      return {pan: {value: 0, setValueAtTime() {}}, connect() {}, disconnect() {}};
    },
    createAnalyser() {
      return {
        fftSize: 256,
        connect() {}, disconnect() {},
        getByteTimeDomainData(buf) { for (let i = 0; i < buf.length; i++) buf[i] = 128; },
      };
    },
    createMediaElementSource() { return {connect() {}, disconnect() {}}; },
    createBufferSource() {
      return {connect() {}, start() {}, stop() {}, buffer: null,
              playbackRate: {value: 1, setValueAtTime() {}}};
    },
    createOscillator() {
      const osc = {
        type: "sine", started: null, stopped: null, _freq: 0,
        frequency: {setValueAtTime(v) { osc._freq = v; }, value: 0},
        connect() {}, disconnect() {},
        start(t) { osc.started = t; },
        stop(t) { osc.stopped = t; },
      };
      return osc;
    },
    decodeAudioData(bytes) {
      // envelope sintética determinística: serve para conferir o desenho
      const n = 4096;
      const ch = new Float32Array(n);
      for (let i = 0; i < n; i++) ch[i] = Math.sin(i / 12) * 0.5;
      return Promise.resolve({getChannelData: () => ch, length: n, duration: 8});
    },
  };
  return ctx;
}

function montar(dados, opcoes) {
  const opts = opcoes || {};
  const html = fs.readFileSync(HTML, "utf8");
  const js = extrairScript(html);
  const doc = new Document();
  const ctx = criarCtx();

  // IDs que o Studio toca de verdade
  const ids = [
    "studio", "studioCorpo", "studioPainel", "painelFaixas", "studioTempo",
    "tempoRolagem", "regua", "linhaCifra", "gradeFaixas", "selecaoTempo",
    "cabecaVertical", "painelInfo", "painelFormula", "studioNome", "studioIcone",
    "studioTom", "studioBpm", "studioDur", "masterVol", "masterVal",
    "playG", "trStop", "trInicio", "trVoltar", "trAvancar", "trAnterior",
    "trProximo", "trLoop", "trSecao", "trAtual", "trTotal", "trCompasso",
    "trTom", "trBpm", "trContagem", "trContagemTexto", "studioSalvo", "legendaStudio",
    "fCompasso", "fBpm", "fTom", "fTomMenos", "fTomMais", "fZoomRange",
    "fZoomMenos", "fZoomMais", "fZoomTudo", "fWavZoom", "fAltura", "fMenu",
    "fMetro", "fLoop", "fMarcar", "fImportarFaixa", "fImportarInput",
    "expMix", "expProjeto", "expPasta", "expAtalho", "expLR", "expClique",
    "expGuia", "expRelatorio", "menuExportar", "studioExportar",
    "studioAoVivo", "ferrDica", "cifraEditar", "dicaFlutuante",
  ];
  for (const id of ids) {
    const el = doc.criar(id, id === "fImportarInput" ? "input" : "div");
    if (id === "fCompasso") el.value = "4/4";
  }
  // o corpo do studio precisa de métricas previsíveis
  doc.getElementById("studioCorpo").clientWidth = 900;
  doc.getElementById("studioTempo").clientWidth = 664;
  doc.getElementById("gradeFaixas").innerHTML = "";

  const avisos = [];
  const sandbox = {
    document: doc,
    window: null,
    location: {origin: "http://localhost:8765", href: "http://localhost:8765/"},
    console: {log: (...a) => avisos.push(a.join(" ")), warn: (...a) => avisos.push(a.join(" ")),
              error: (...a) => avisos.push(a.join(" "))},
    AudioContext: function () { return ctx; },
    Audio: function () { return new AudioEl(doc); },
    requestAnimationFrame: (fn) => { sandbox.__raf = fn; return 1; },
    cancelAnimationFrame: () => {},
    setTimeout: (fn, ms) => { sandbox.__timers.push({fn, ms}); return sandbox.__timers.length; },
    clearTimeout: () => {},
    clearInterval: () => {},
    setInterval: () => 0,
    fetch: opts.fetch || (() => Promise.resolve({ok: false, status: 404, json: () => Promise.resolve({})})),
    alert: (msg) => avisos.push("alert: " + msg),
    localStorage: {getItem: () => null, setItem: () => {}},
    getComputedStyle: () => ({getPropertyValue: (k) => (k === "--h-linha" ? "76px" : "")}),
    URL: URL,
    Math, JSON, Object, Array, Number, String, Boolean, Float32Array, Uint8Array,
    isFinite, parseInt, parseFloat, Promise, Error, RegExp, Date, Set, Map,
    performance: {now: () => Date.now()},
  };
  sandbox.__timers = [];
  sandbox.addEventListener = () => {};
  sandbox.removeEventListener = () => {};
  sandbox.devicePixelRatio = 1;
  sandbox.innerWidth = 1440;
  sandbox.innerHeight = 900;
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  // o HTML original só define handlers; para o teste precisamos de stubs
  sandbox.__avisos = avisos;
  sandbox.__ctx = ctx;
  sandbox.__timers = [];

  const script = new vm.Script(js, {filename: "index.html<script>"});
  vm.createContext(sandbox);
  script.runInContext(sandbox, {timeout: 20000});
  const Studio = sandbox.Studio;
  // o `studioLigarBotoes()` do fim do arquivo roda no load: basta
  sandbox.__run = script;
  if (dados) Studio && Studio.dados === null && sandbox.studioMontar && sandbox.studioMontar(dados);
  return {sandbox, Studio, doc, ctx, avisos};
}

module.exports = {montar, extrairScript, criarCtx};
