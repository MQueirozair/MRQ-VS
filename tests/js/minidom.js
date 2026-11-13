// Mini-DOM em Node para executar o JS do Studio sem navegador.
//
// Serve aos testes de verdade: o código que roda aqui é o mesmo que o navegador
// executa (extraído do <script> do index.html), só que com um DOM mínimo.
// `harness.js` monta o documento com os IDs do Studio e chama `montar(dados)`.

class ClassList {
  constructor(el) { this.el = el; this.set = new Set(); }
  add(...c) { c.filter(Boolean).forEach((x) => this.set.add(x)); }
  remove(...c) { c.forEach((x) => this.set.delete(x)); }
  contains(c) { return this.set.has(c); }
  toggle(c, on) {
    const v = on === undefined ? !this.set.has(c) : !!on;
    if (v) this.set.add(c); else this.set.delete(c);
    return v;
  }
  get value() { return [...this.set].join(" "); }
}

class El {
  constructor(tag, doc) {
    this.tagName = String(tag || "div").toUpperCase();
    this.ownerDocument = doc;
    this.children = [];
    this.parentElement = null;
    const estilo = {};
    estilo.setProperty = (k, v) => { estilo[k] = v; };
    estilo.getPropertyValue = (k) => estilo[k] || "";
    this.style = estilo;
    this.dataset = {};
    this.classList = new ClassList(this);
    this._attrs = {};
    this._html = "";
    this.textContent = "";
    this.value = "";
    this.checked = false;
    this.hidden = false;
    this.disabled = false;
    this.scrollLeft = 0;
    this.scrollTop = 0;
    this.clientWidth = 900;
    this.clientHeight = 76;
    this.offsetWidth = 240;
    this.offsetHeight = 140;
    this.width = 0;
    this.height = 0;
    this.href = "#";
    this.src = "";
    this.files = [];
    this.paused = true;
    this.currentTime = 0;
    this.duration = NaN;
    this.muted = false;
    this.volume = 1;
  }
  get id() { return this._attrs.id || ""; }
  set id(v) { this._attrs.id = v; }
  get className() { return this.classList.value; }
  set className(v) { this.classList.set = new Set(String(v || "").split(/\s+/).filter(Boolean)); }
  get options() { return this.children.filter((c) => c.tagName === "OPTION"); }
  set innerHTML(v) {
    this._html = String(v == null ? "" : v);
    this.children = [];
    const re = /<(div|span|input|button|option|canvas|svg|i|label|small|b)\b([^>]*)>/g;
    let m;
    while ((m = re.exec(this._html))) {
      const el = new El(m[1], this.ownerDocument);
      const attrs = m[2] || "";
      const idm = /id="([^"]*)"/.exec(attrs);
      if (idm) el.id = idm[1];
      const cl = /class="([^"]*)"/.exec(attrs);
      if (cl) el.className = cl[1];
      const val = /value="([^"]*)"/.exec(attrs);
      if (val) el.value = val[1];
      // data-* vira dataset (o Studio lê compasso/inicio/agrupado por ali)
      const reData = /data-([\w-]+)="([^"]*)"/g;
      let d;
      while ((d = reData.exec(attrs))) {
        const chave = d[1].replace(/-([a-z])/g, (_, c) => c.toUpperCase());
        el.dataset[chave] = d[2];
        el._attrs["data-" + d[1]] = d[2];
      }
      // texto entre a tag de abertura e a próxima tag
      const resto = this._html.slice(m.index + m[0].length);
      const fecha = resto.indexOf("<");
      el._texto = (fecha < 0 ? resto : resto.slice(0, fecha)).trim();
      Object.defineProperty(el, "textContent", {
        get() { return el._texto || ""; },
        set(v) { el._texto = String(v); },
        configurable: true,
      });
      el.parentElement = this;
      this.children.push(el);
    }
  }
  get innerHTML() { return this._html; }
  appendChild(el) { el.parentElement = this; this.children.push(el); return el; }
  insertBefore(el, ref) {
    el.parentElement = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(el); else this.children.splice(i, 0, el);
    return el;
  }
  removeChild(el) {
    const i = this.children.indexOf(el);
    if (i >= 0) this.children.splice(i, 1);
    el.parentElement = null;
    return el;
  }
  remove() { if (this.parentElement) this.parentElement.removeChild(this); }
  setAttribute(k, v) { this._attrs[k] = String(v); if (k === "class") this.className = v; }
  getAttribute(k) { return this._attrs[k] == null ? null : this._attrs[k]; }
  removeAttribute(k) { delete this._attrs[k]; }
  addEventListener() {}
  removeEventListener() {}
  getBoundingClientRect() {
    return {left: 0, top: 0, right: this.clientWidth, bottom: this.clientHeight,
            width: this.clientWidth, height: this.clientHeight};
  }
  getContext() { return ctx2dFake(); }
  click() { if (this.onclick) this.onclick({stopPropagation() {}, preventDefault() {}, target: this}); }
  focus() {}
  select() {}
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; }
  load() {}
  closest() { return null; }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    const out = [];
    const passo = (el) => {
      for (const c of el.children) {
        if (casa(c, sel)) out.push(c);
        passo(c);
      }
    };
    passo(this);
    return out;
  }
}

function casa(el, sel) {
  if (!sel) return false;
  const partes = String(sel).trim().split(",");
  for (const p of partes) {
    const s = p.trim();
    if (!s) continue;
    if (s.includes(" ") || s.includes(">")) {
      const final = s.split(/[\s>]+/).pop();
      if (casa(el, final)) {
        const pai = el.parentElement;
        if (!pai) continue;
        const amb = s.split(/[\s>]+/).slice(0, -1).join(" ");
        if (!amb || casa(pai, amb)) return true;
      }
      continue;
    }
    if (s.startsWith(".")) {
      if (el.classList.contains(s.slice(1).split(/[.:\[]/)[0])) return true;
      continue;
    }
    if (s.startsWith("#")) {
      if (el.id === s.slice(1)) return true;
      continue;
    }
    if (s.startsWith("[")) {
      const m = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(s);
      if (m && el._attrs[m[1]] != null && (m[2] == null || el._attrs[m[1]] === m[2])) return true;
      continue;
    }
    const tag = s.split(/[.:\[]/)[0];
    if (tag && el.tagName === tag.toUpperCase()) return true;
  }
  return false;
}

function ctx2dFake() {
  const noop = () => {};
  return {
    globalAlpha: 1, fillStyle: "#000", font: "", strokeStyle: "#000", lineWidth: 1,
    clearRect: noop, fillRect: noop, fillText: noop, strokeRect: noop,
    beginPath: noop, moveTo: noop, lineTo: noop, stroke: noop, fill: noop,
    setTransform: noop, save: noop, restore: noop,
    measureText: () => ({width: 8}),
  };
}

// `new Audio()` do navegador: um <audio> de verdade para o Studio controlar
class AudioEl extends El {
  constructor(doc) {
    super("audio", doc);
    this.paused = true;
    this.currentTime = 0;
    this.duration = 30;
    this.preload = "";
    this.crossOrigin = "";
    this._listeners = {};
  }
  play() {
    this.paused = false;
    return Promise.resolve();
  }
  pause() { this.paused = true; }
  load() {}
  removeAttribute() {}
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); }
}

class Document {
  constructor() {
    this.body = new El("body", this);
    this.documentElement = new El("html", this);
    this.documentElement.style.setProperty("--h-linha", "76px");
    this._ids = new Map();
    this.activeElement = null;
    this._listeners = {};
  }
  createElement(tag) { return new El(tag, this); }
  getElementById(id) {
    if (!this._ids.has(id)) {
      const el = new El("div", this);
      el.id = id;
      el._attrs.id = id;
      this.body.appendChild(el);
      this._ids.set(id, el);
    }
    return this._ids.get(id);
  }
  criar(id, tag) {
    const el = new El(tag || "div", this);
    el.id = id;
    el._attrs.id = id;
    this.body.appendChild(el);
    this._ids.set(id, el);
    return el;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  querySelectorAll(sel) {
    const out = [];
    const passo = (el) => {
      for (const c of el.children) { if (casa(c, sel)) out.push(c); passo(c); }
    };
    passo(this.body);
    return out;
  }
  addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); }
  removeEventListener() {}
}

module.exports = {El, Document, AudioEl};
