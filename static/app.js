/* VideoCoder Studio — SPA Vue 3 + Vue Router */

const { createApp } = Vue;
const { createRouter, createWebHashHistory } = VueRouter;

const API = "";

/* ---------------------------------------------------------- helpers */

function fmtSize(octets) {
  if (octets == null) return "";
  const unites = ["o", "Ko", "Mo", "Go"];
  let i = 0;
  while (octets >= 1024 && i < 3) { octets /= 1024; i++; }
  return octets.toFixed(i ? 1 : 0) + " " + unites[i];
}

function fmtDur(s) {
  if (s == null) return "";
  s = Math.round(s);
  const m = Math.floor(s / 60), sec = s % 60;
  return m + ":" + String(sec).padStart(2, "0");
}

/* ---------------------------------------------------------- FilePicker */

const FilePicker = {
  props: { kind: { type: String, default: "videos" } },
  emits: ["select"],
  data: () => ({ files: [], selected: null, loading: true }),
  computed: {
    label() {
      return this.kind === "audios" ? "Audios dans audio/" : "Vidéos dans downloads/";
    },
    vide() {
      return this.kind === "audios"
        ? "Aucun audio. Extrayez-en un ou enregistrez une radio."
        : "Aucune vidéo. Téléchargez-en une depuis l'onglet YouTube.";
    },
    icone() { return this.kind === "audios" ? "fa-music" : "fa-film"; },
  },
  async created() { await this.reload(); },
  methods: {
    async reload() {
      this.loading = true;
      const { data } = await axios.get(API + "/api/files");
      this.files = data[this.kind];
      this.loading = false;
    },
    pick(v) {
      this.selected = v.name;
      this.$emit("select", v);
    },
    fmtSize, fmtDur,
  },
  template: `
    <div>
      <div class="d-flex justify-content-between align-items-center mb-2">
        <span class="vc-label">{{ label }}</span>
        <button class="btn btn-ghost btn-sm" @click="reload" title="Actualiser">
          <i class="fa-solid fa-rotate"></i>
        </button>
      </div>
      <p v-if="loading" class="text-secondary mb-0">Chargement…</p>
      <p v-else-if="!files.length" class="text-secondary mb-0">{{ vide }}</p>
      <div v-else class="vc-files">
        <button v-for="v in files" :key="v.name" type="button"
                class="vc-file" :class="{selected: v.name === selected}"
                @click="pick(v)">
          <i class="fa-solid" :class="icone"></i>
          <span class="name">{{ v.name }}</span>
          <span class="meta vc-mono">
            <template v-if="v.duration != null">{{ fmtDur(v.duration) }} · </template>{{ fmtSize(v.size) }}
          </span>
        </button>
      </div>
    </div>`,
};

/* ---------------------------------------------------------- TaskProgress */

const TaskProgress = {
  props: { taskId: String, stoppable: Boolean },
  emits: ["done"],
  data: () => ({ task: null, timer: null }),
  watch: {
    taskId: { immediate: true, handler(id) { this.stopPoll(); if (id) this.poll(); } },
  },
  unmounted() { this.stopPoll(); },
  methods: {
    stopPoll() { if (this.timer) { clearInterval(this.timer); this.timer = null; } },
    poll() {
      const tick = async () => {
        const { data } = await axios.get(API + "/api/tasks/" + this.taskId);
        this.task = data;
        if (data.status !== "running" && data.status !== "queued") {
          this.stopPoll(); this.$emit("done", data);
        }
      };
      tick();
      this.timer = setInterval(tick, 800);
    },
    fmtSize,
    mediaUrl(o) { return API + "/api/media/" + o.type + "/" + encodeURIComponent(o.name); },
    async stopTask() { await axios.post(API + "/api/tasks/" + this.taskId + "/stop"); },
  },
  template: `
    <div v-if="task" class="mt-3">
      <div v-if="task.status === 'running' || task.status === 'queued'">
        <div class="d-flex justify-content-between mb-1">
          <span class="vc-label">
            <i v-if="task.status === 'queued'" class="fa-solid fa-hourglass-half me-1"></i>{{ task.message }}
          </span>
          <span class="vc-mono">{{ task.progress }} %</span>
        </div>
        <div class="vc-progress"><div class="bar" :style="{width: task.progress + '%'}"></div></div>
        <button v-if="stoppable && task.status === 'running'" class="btn btn-ghost btn-sm mt-2" @click="stopTask">
          <i class="fa-solid fa-stop me-1"></i>Arrêter (garde le fichier)
        </button>
      </div>
      <div v-else-if="task.status === 'done'" class="vc-result">
        <div class="d-flex align-items-center gap-2">
          <i class="fa-solid fa-circle-check"></i>
          <span class="name flex-grow-1 text-truncate">{{ task.output.name }}</span>
          <span class="vc-mono">{{ fmtSize(task.output.size) }}</span>
          <a class="btn btn-ghost btn-sm" :href="mediaUrl(task.output)" target="_blank"
             title="Ouvrir le fichier"><i class="fa-solid fa-arrow-up-right-from-square"></i></a>
        </div>
        <div v-for="w in task.output.warnings" :key="w" class="vc-warning mt-2">
          <i class="fa-solid fa-triangle-exclamation me-1"></i>{{ w }}
        </div>
      </div>
      <div v-else class="vc-error mt-2">
        <i class="fa-solid fa-circle-xmark me-1"></i>{{ task.message }}
      </div>
    </div>`,
};

/* ---------------------------------------------------------- vues */

const DownloadView = {
  components: { TaskProgress },
  data: () => ({ url: "", info: null, infoLoading: false, error: "", taskId: null }),
  methods: {
    fmtDur,
    async fetchInfo() {
      this.error = ""; this.info = null; this.taskId = null;
      if (!this.url.trim()) return;
      this.infoLoading = true;
      try {
        const { data } = await axios.post(API + "/api/youtube/info", { url: this.url });
        this.info = data;
      } catch (e) {
        this.error = e.response?.data?.error || "Erreur réseau";
      }
      this.infoLoading = false;
    },
    async download() {
      const { data } = await axios.post(API + "/api/youtube/download", { url: this.url });
      this.taskId = data.task_id;
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Étape 1 — Récupérer</span>
        <h1>Téléchargement YouTube</h1>
        <p>Collez un lien : la vidéo est vérifiée puis enregistrée en MP4 dans le dossier downloads.</p>
      </header>
      <div class="vc-card">
        <form @submit.prevent="fetchInfo" class="d-flex gap-2 flex-wrap">
          <input v-model="url" type="url" class="form-control flex-grow-1" style="min-width:220px"
                 placeholder="https://www.youtube.com/watch?v=…" required>
          <button class="btn btn-vc" :disabled="infoLoading">
            <i class="fa-solid fa-magnifying-glass me-1"></i>
            {{ infoLoading ? "Vérification…" : "Vérifier" }}
          </button>
        </form>
        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>

        <div v-if="info" class="mt-4 d-flex gap-3 flex-wrap">
          <img v-if="info.thumbnail" :src="info.thumbnail" class="vc-thumb" alt="Miniature">
          <div class="flex-grow-1">
            <dl class="vc-meta-grid mb-3">
              <dt>Titre</dt><dd>{{ info.title }}</dd>
              <dt>Chaîne</dt><dd>{{ info.uploader }}</dd>
              <dt>Durée</dt><dd class="vc-mono">{{ fmtDur(info.duration) }}</dd>
              <dt>Vues</dt><dd class="vc-mono">{{ info.views?.toLocaleString("fr-FR") }}</dd>
            </dl>
            <button class="btn btn-vc" @click="download" :disabled="!!taskId">
              <i class="fa-solid fa-download me-1"></i>Télécharger en MP4
            </button>
          </div>
        </div>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const ConvertView = {
  components: { FilePicker, TaskProgress },
  data: () => ({ file: null, taskId: null, error: "" }),
  methods: {
    async convert() {
      this.error = ""; this.taskId = null;
      try {
        const { data } = await axios.post(API + "/api/convert", { file: this.file.name });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Réseaux sociaux</span>
        <h1>Conversion WhatsApp / Instagram</h1>
        <p>Ré-encode en H.264 + AAC avec un débit calé sur la durée pour viser
           moins de 16 Mo, prêt à partager en message, statut ou Reel.</p>
      </header>
      <div class="vc-card">
        <file-picker @select="f => { file = f; taskId = null }"></file-picker>
        <button class="btn btn-vc mt-3" :disabled="!file" @click="convert">
          <i class="fa-brands fa-whatsapp me-1"></i>Convertir
        </button>
        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const AudioView = {
  components: { FilePicker, TaskProgress },
  data: () => ({ file: null, format: "mp3", taskId: null, error: "",
                 formats: ["mp3", "aac", "ogg", "wav", "flac"] }),
  methods: {
    async extract() {
      this.error = ""; this.taskId = null;
      try {
        const { data } = await axios.post(API + "/api/audio/extract",
                                          { file: this.file.name, format: this.format });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Piste son</span>
        <h1>Extraction audio</h1>
        <p>Isole la piste audio d'une vidéo vers le dossier audio, au format de votre choix.</p>
      </header>
      <div class="vc-card">
        <file-picker @select="f => { file = f; taskId = null }"></file-picker>
        <div class="d-flex gap-2 align-items-end mt-3 flex-wrap">
          <div>
            <label class="vc-label d-block mb-1" for="fmt">Format</label>
            <select id="fmt" v-model="format" class="form-select" style="width:auto">
              <option v-for="f in formats" :key="f" :value="f">{{ f }}</option>
            </select>
          </div>
          <button class="btn btn-vc" :disabled="!file" @click="extract">
            <i class="fa-solid fa-music me-1"></i>Extraire l'audio
          </button>
        </div>
        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const CutView = {
  components: { FilePicker, TaskProgress },
  data: () => ({
    file: null, thumbs: null, dur: 0,
    t1s: 0, t2s: 0, cur: 0,
    t1txt: "0:00", t2txt: "0:00",
    taskId: null, error: "",
  }),
  async created() {
    // Lien direct : #/cut?file=<nom> présélectionne la vidéo
    const nom = this.$route.query.file;
    if (nom) {
      const { data } = await axios.get(API + "/api/files");
      const f = data.videos.find(v => v.name === nom);
      if (f) this.pick(f);
    }
  },
  computed: {
    videoUrl() {
      return this.file ? API + "/api/media/video/" + encodeURIComponent(this.file.name) : "";
    },
    selStyle() {
      if (!this.dur) return {};
      return {
        left: (this.t1s / this.dur * 100) + "%",
        width: (Math.max(0, this.t2s - this.t1s) / this.dur * 100) + "%",
      };
    },
  },
  methods: {
    fmtDur,
    async pick(f) {
      this.file = f; this.taskId = null; this.error = ""; this.thumbs = null;
      try {
        const { data } = await axios.post(API + "/api/thumbnails", { file: f.name });
        this.thumbs = data;
        this.dur = data.duration;
        this.setT1(0); this.setT2(this.dur); this.cur = 0;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
    thumbUrl(i) { return API + "/api/thumb/" + this.thumbs.hash + "/" + i; },
    seek(ev) {
      const r = ev.currentTarget.getBoundingClientRect();
      const t = (ev.clientX - r.left) / r.width * this.dur;
      const vid = this.$refs.vid;
      if (vid) vid.currentTime = Math.max(0, Math.min(t, this.dur));
    },
    setT1(t) { this.t1s = Math.max(0, Math.min(t, this.dur)); this.t1txt = fmtDur(this.t1s); },
    setT2(t) { this.t2s = Math.max(0, Math.min(t, this.dur)); this.t2txt = fmtDur(this.t2s); },
    parseTxt(s) {
      s = String(s).trim().replace(",", ".");
      const m = s.match(/^(\d+):([0-5]?\d)$/);
      if (m) return +m[1] * 60 + +m[2];
      const f = parseFloat(s);
      return isNaN(f) ? null : f * 60;
    },
    editT1() { const t = this.parseTxt(this.t1txt); if (t != null) this.setT1(t); },
    editT2() { const t = this.parseTxt(this.t2txt); if (t != null) this.setT2(t); },
    async cut() {
      this.error = ""; this.taskId = null;
      if (this.t2s <= this.t1s) { this.error = "La fin doit être après le début."; return; }
      try {
        const { data } = await axios.post(API + "/api/cut",
          { file: this.file.name, t1: this.t1s, t2: this.t2s });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Montage</span>
        <h1>Découpage</h1>
        <p>Regardez la vidéo, cliquez sur la timeline pour vous déplacer, puis marquez
           le début et la fin de la partie à garder — pratique pour sauter une pub.</p>
      </header>
      <div class="vc-card">
        <file-picker @select="pick"></file-picker>

        <div v-if="thumbs" class="mt-3">
          <video ref="vid" :src="videoUrl" controls class="vc-player"
                 @timeupdate="cur = $event.target.currentTime"></video>

          <div class="vc-timeline mt-2" @click="seek" title="Cliquer pour se déplacer">
            <img v-for="i in thumbs.count" :key="i" :src="thumbUrl(i)" alt="">
            <div class="sel" :style="selStyle"></div>
            <div class="playhead" :style="{left: (dur ? cur/dur*100 : 0) + '%'}"></div>
          </div>
          <div class="vc-timecodes vc-mono">
            <span>0:00</span>
            <span>lecture : {{ fmtDur(cur) }}</span>
            <span>{{ fmtDur(dur) }}</span>
          </div>

          <div class="d-flex gap-2 align-items-end mt-3 flex-wrap">
            <button class="btn btn-ghost" @click="setT1(cur)" title="Marquer le début à la position de lecture">
              <i class="fa-solid fa-arrow-right-to-bracket me-1"></i>Début ici
            </button>
            <button class="btn btn-ghost" @click="setT2(cur)" title="Marquer la fin à la position de lecture">
              <i class="fa-solid fa-arrow-right-from-bracket me-1"></i>Fin ici
            </button>
            <div>
              <label class="vc-label d-block mb-1" for="t1">Début</label>
              <input id="t1" v-model="t1txt" @change="editT1"
                     class="form-control vc-mono" style="width:7rem">
            </div>
            <div>
              <label class="vc-label d-block mb-1" for="t2">Fin</label>
              <input id="t2" v-model="t2txt" @change="editT2"
                     class="form-control vc-mono" style="width:7rem">
            </div>
            <button class="btn btn-vc" :disabled="t2s <= t1s" @click="cut">
              <i class="fa-solid fa-scissors me-1"></i>Découper
              <span class="vc-mono ms-1">({{ fmtDur(t2s - t1s) }})</span>
            </button>
          </div>
        </div>

        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const RadioView = {
  components: { TaskProgress },
  data: () => ({
    stations: [], station: null, customUrl: "", customName: "",
    minutes: 10, taskId: null, error: "",
    playing: false, nowPlaying: null, npTimer: null,
  }),
  async created() {
    const { data } = await axios.get(API + "/api/radio/stations");
    this.stations = data;
  },
  unmounted() { this.stopListen(); },
  computed: {
    urlActive() { return this.station ? this.station.url : this.customUrl.trim(); },
    nomActif() {
      return this.station ? this.station.name : (this.customName.trim() || "radio");
    },
  },
  methods: {
    pick(s) {
      if (this.playing) this.stopListen();
      this.station = s;
      this.customUrl = "";
      this.taskId = null;
    },
    toggleListen() {
      if (this.playing) { this.stopListen(); return; }
      if (!this.urlActive) return;
      const audio = this.$refs.player;
      audio.src = this.urlActive;
      audio.play().then(() => {
        this.playing = true;
        this.fetchNowPlaying();
        this.npTimer = setInterval(this.fetchNowPlaying, 15000);
      }).catch(() => { this.error = "Impossible de lire ce flux dans le navigateur."; });
    },
    stopListen() {
      const audio = this.$refs.player;
      if (audio) { audio.pause(); audio.removeAttribute("src"); audio.load(); }
      this.playing = false;
      this.nowPlaying = null;
      if (this.npTimer) { clearInterval(this.npTimer); this.npTimer = null; }
    },
    async fetchNowPlaying() {
      try {
        const { data } = await axios.get(API + "/api/radio/nowplaying",
                                         { params: { url: this.urlActive } });
        this.nowPlaying = data;
      } catch { this.nowPlaying = null; }
    },
    async record() {
      this.error = ""; this.taskId = null;
      try {
        const { data } = await axios.post(API + "/api/radio/record", {
          url: this.urlActive, name: this.nomActif, minutes: this.minutes,
        });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Direct</span>
        <h1>Radio — écoute et enregistrement</h1>
        <p>Choisissez une station marocaine ou collez l'URL d'un flux, écoutez en direct
           et enregistrez la durée voulue en MP3 dans le dossier audio.</p>
      </header>

      <div class="vc-card mb-3">
        <span class="vc-label d-block mb-2">Stations ({{ stations.length }})</span>
        <div class="vc-files" style="max-height:260px">
          <button v-for="s in stations" :key="s.url" type="button"
                  class="vc-file" :class="{selected: station && station.url === s.url}"
                  @click="pick(s)">
            <i class="fa-solid fa-tower-broadcast"></i>
            <span class="name">{{ s.name }}</span>
            <span class="meta">{{ s.genre }}</span>
          </button>
        </div>
        <div class="mt-3">
          <span class="vc-label d-block mb-1">Ou un flux personnalisé</span>
          <div class="d-flex gap-2 flex-wrap">
            <input v-model="customUrl" @input="station = null" type="url"
                   class="form-control flex-grow-1" style="min-width:220px"
                   placeholder="https://…/stream.mp3">
            <input v-model="customName" class="form-control" style="width:12rem"
                   placeholder="Nom (fichier)">
          </div>
        </div>
      </div>

      <div class="vc-card">
        <div class="d-flex gap-2 align-items-end flex-wrap">
          <button class="btn btn-ghost" :disabled="!urlActive" @click="toggleListen">
            <i class="fa-solid me-1" :class="playing ? 'fa-stop' : 'fa-play'"></i>
            {{ playing ? "Arrêter l'écoute" : "Écouter" }}
          </button>
          <div>
            <label class="vc-label d-block mb-1" for="mn">Durée (minutes)</label>
            <input id="mn" v-model.number="minutes" type="number" min="1" max="240"
                   class="form-control vc-mono" style="width:8rem">
          </div>
          <button class="btn btn-vc" :disabled="!urlActive || !minutes" @click="record">
            <i class="fa-solid fa-circle-dot me-1"></i>Enregistrer en MP3
          </button>
        </div>

        <div v-if="playing" class="mt-3 d-flex align-items-center gap-2 flex-wrap">
          <span class="badge" style="background:var(--vc-err)">
            <i class="fa-solid fa-circle me-1" style="font-size:.55em"></i>EN DIRECT
          </span>
          <strong>{{ nowPlaying?.station || nomActif }}</strong>
          <span v-if="nowPlaying?.title" class="text-secondary">
            <i class="fa-solid fa-music mx-1"></i>{{ nowPlaying.title }}
          </span>
          <span v-if="nowPlaying?.bitrate" class="vc-mono text-secondary">
            {{ nowPlaying.bitrate }} kb/s
          </span>
        </div>

        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId" stoppable></task-progress>
        <audio ref="player" preload="none"></audio>
      </div>
    </div>`,
};

const FramesView = {
  components: { FilePicker, TaskProgress },
  data: () => ({ file: null, format: "jpg", every: 1, taskId: null, error: "" }),
  methods: {
    async run() {
      this.error = ""; this.taskId = null;
      try {
        const { data } = await axios.post(API + "/api/frames", {
          file: this.file.name, format: this.format, every: this.every,
        });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Photogrammes</span>
        <h1>Découpage en images</h1>
        <p>Extrait une image toutes les N secondes, en JPEG ou PNG,
           livrées dans une archive ZIP.</p>
      </header>
      <div class="vc-card">
        <file-picker @select="f => { file = f; taskId = null }"></file-picker>
        <div class="d-flex gap-2 align-items-end mt-3 flex-wrap">
          <div>
            <label class="vc-label d-block mb-1" for="ev">Intervalle (s)</label>
            <input id="ev" v-model.number="every" type="number" min="0.1" step="0.1"
                   class="form-control vc-mono" style="width:8rem">
          </div>
          <div>
            <label class="vc-label d-block mb-1" for="ff">Format</label>
            <select id="ff" v-model="format" class="form-select" style="width:auto">
              <option value="jpg">jpeg</option>
              <option value="png">png</option>
            </select>
          </div>
          <button class="btn btn-vc" :disabled="!file || !every" @click="run">
            <i class="fa-solid fa-images me-1"></i>Extraire les images
          </button>
        </div>
        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const MusicView = {
  components: { FilePicker, TaskProgress },
  data: () => ({ video: null, audio: null, mode: "replace", taskId: null, error: "" }),
  methods: {
    async run() {
      this.error = ""; this.taskId = null;
      try {
        const { data } = await axios.post(API + "/api/music", {
          video: this.video.name, audio: this.audio.name, mode: this.mode,
        });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Habillage sonore</span>
        <h1>Bande musicale</h1>
        <p>Associe une piste du dossier audio à une vidéo : en remplacement du son
           d'origine, ou mixée avec lui. La sortie s'arrête à la piste la plus courte.</p>
      </header>
      <div class="vc-card mb-3">
        <file-picker @select="f => { video = f; taskId = null }"></file-picker>
      </div>
      <div class="vc-card">
        <file-picker kind="audios" @select="f => { audio = f; taskId = null }"></file-picker>
        <div class="d-flex gap-2 align-items-end mt-3 flex-wrap">
          <div>
            <label class="vc-label d-block mb-1" for="md">Mode</label>
            <select id="md" v-model="mode" class="form-select" style="width:auto">
              <option value="replace">Remplacer le son d'origine</option>
              <option value="mix">Mixer avec le son d'origine</option>
            </select>
          </div>
          <button class="btn btn-vc" :disabled="!video || !audio" @click="run">
            <i class="fa-solid fa-wand-magic-sparkles me-1"></i>Associer
          </button>
        </div>
        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const TextView = {
  components: { FilePicker, TaskProgress },
  data: () => ({
    file: null, text: "", position: "bottom", color: "white",
    taskId: null, error: "",
    positions: [["top", "Haut"], ["center", "Centre"], ["bottom", "Bas"]],
    colors: [["white", "Blanc"], ["yellow", "Jaune"], ["black", "Noir"],
             ["red", "Rouge"], ["orange", "Orange"]],
  }),
  methods: {
    async run() {
      this.error = ""; this.taskId = null;
      try {
        const { data } = await axios.post(API + "/api/text", {
          file: this.file.name, text: this.text,
          position: this.position, color: this.color,
        });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Habillage visuel</span>
        <h1>Titre sur la vidéo</h1>
        <p>Incruste un texte centré, avec contour noir pour rester lisible
           sur n'importe quelle image.</p>
      </header>
      <div class="vc-card">
        <file-picker @select="f => { file = f; taskId = null }"></file-picker>
        <div class="mt-3">
          <label class="vc-label d-block mb-1" for="tx">Texte du titre</label>
          <input id="tx" v-model="text" class="form-control" maxlength="120"
                 placeholder="Mon titre…">
        </div>
        <div class="d-flex gap-2 align-items-end mt-3 flex-wrap">
          <div>
            <label class="vc-label d-block mb-1" for="pos">Position</label>
            <select id="pos" v-model="position" class="form-select" style="width:auto">
              <option v-for="[v, l] in positions" :key="v" :value="v">{{ l }}</option>
            </select>
          </div>
          <div>
            <label class="vc-label d-block mb-1" for="col">Couleur</label>
            <select id="col" v-model="color" class="form-select" style="width:auto">
              <option v-for="[v, l] in colors" :key="v" :value="v">{{ l }}</option>
            </select>
          </div>
          <button class="btn btn-vc" :disabled="!file || !text.trim()" @click="run">
            <i class="fa-solid fa-heading me-1"></i>Incruster le titre
          </button>
        </div>
        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const EffectsView = {
  components: { FilePicker, TaskProgress },
  data: () => ({
    file: null, effects: [], effect: "fadeblack", where: "intro",
    duration: 2, taskId: null, error: "",
    wheres: [["intro", "Début de la vidéo"], ["outro", "Fin de la vidéo"],
             ["both", "Début et fin"]],
  }),
  async created() {
    const { data } = await axios.get(API + "/api/effects");
    this.effects = data;
  },
  methods: {
    async run() {
      this.error = ""; this.taskId = null;
      try {
        const { data } = await axios.post(API + "/api/effects", {
          file: this.file.name, effect: this.effect,
          where: this.where, duration: Number(this.duration) || 2,
        });
        this.taskId = data.task_id;
      } catch (e) { this.error = e.response?.data?.error || "Erreur réseau"; }
    },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Habillage visuel</span>
        <h1>Effets d'intro / outro</h1>
        <p>Ajoute une transition d'ouverture ou de fermeture (fondu, cercle,
           zoom…) sur la vidéo, avec fondu du son assorti.</p>
      </header>
      <div class="vc-card">
        <file-picker @select="f => { file = f; taskId = null }"></file-picker>
        <div class="d-flex gap-2 align-items-end mt-3 flex-wrap">
          <div>
            <label class="vc-label d-block mb-1" for="fx">Effet</label>
            <select id="fx" v-model="effect" class="form-select" style="width:auto">
              <option v-for="e in effects" :key="e.id" :value="e.id">{{ e.label }}</option>
            </select>
          </div>
          <div>
            <label class="vc-label d-block mb-1" for="ou">Appliquer</label>
            <select id="ou" v-model="where" class="form-select" style="width:auto">
              <option v-for="[v, l] in wheres" :key="v" :value="v">{{ l }}</option>
            </select>
          </div>
          <div>
            <label class="vc-label d-block mb-1" for="dur">Durée (s)</label>
            <input id="dur" v-model="duration" type="number" min="0.5" max="5"
                   step="0.5" class="form-control" style="width:6rem">
          </div>
          <button class="btn btn-vc" :disabled="!file" @click="run">
            <i class="fa-solid fa-wand-magic-sparkles me-1"></i>Appliquer l'effet
          </button>
        </div>
        <p v-if="error" class="vc-error mt-3 mb-0">{{ error }}</p>
        <task-progress :task-id="taskId"></task-progress>
      </div>
    </div>`,
};

const LibraryView = {
  data: () => ({ videos: [], audios: [], exports: [] }),
  async created() {
    const { data } = await axios.get(API + "/api/files");
    this.videos = data.videos;
    this.audios = data.audios;
    this.exports = data.exports || [];
  },
  methods: {
    fmtSize, fmtDur,
    url(type, name) { return API + "/api/media/" + type + "/" + encodeURIComponent(name); },
  },
  template: `
    <div>
      <header>
        <span class="vc-label">Fichiers</span>
        <h1>Bibliothèque</h1>
        <p>Tout ce que l'atelier a produit : vidéos dans downloads, pistes dans audio.</p>
      </header>
      <div class="vc-card mb-3">
        <span class="vc-label d-block mb-2">Vidéos ({{ videos.length }})</span>
        <div class="vc-files">
          <a v-for="v in videos" :key="v.name" class="vc-file text-decoration-none"
             :href="url('video', v.name)" target="_blank">
            <i class="fa-solid fa-film"></i>
            <span class="name">{{ v.name }}</span>
            <span class="meta vc-mono">{{ fmtDur(v.duration) }} · {{ fmtSize(v.size) }}</span>
          </a>
        </div>
      </div>
      <div class="vc-card mb-3">
        <span class="vc-label d-block mb-2">Audios ({{ audios.length }})</span>
        <div class="vc-files">
          <a v-for="a in audios" :key="a.name" class="vc-file text-decoration-none"
             :href="url('audio', a.name)" target="_blank">
            <i class="fa-solid fa-music"></i>
            <span class="name">{{ a.name }}</span>
            <span class="meta vc-mono">{{ fmtSize(a.size) }}</span>
          </a>
        </div>
      </div>
      <div class="vc-card" v-if="exports.length">
        <span class="vc-label d-block mb-2">Exports d'images ({{ exports.length }})</span>
        <div class="vc-files">
          <a v-for="e in exports" :key="e.name" class="vc-file text-decoration-none"
             :href="url('video', e.name)" target="_blank">
            <i class="fa-solid fa-file-zipper"></i>
            <span class="name">{{ e.name }}</span>
            <span class="meta vc-mono">{{ fmtSize(e.size) }}</span>
          </a>
        </div>
      </div>
    </div>`,
};

/* ---------------------------------------------------------- app */

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/youtube" },
    { path: "/youtube", component: DownloadView },
    { path: "/convert", component: ConvertView },
    { path: "/audio", component: AudioView },
    { path: "/cut", component: CutView },
    { path: "/radio", component: RadioView },
    { path: "/frames", component: FramesView },
    { path: "/music", component: MusicView },
    { path: "/text", component: TextView },
    { path: "/effects", component: EffectsView },
    { path: "/library", component: LibraryView },
  ],
});

const app = createApp({
  data: () => ({
    theme: localStorage.getItem("vc-theme") || "dark",
  }),
  watch: {
    theme: {
      immediate: true,
      handler(t) {
        document.documentElement.setAttribute("data-bs-theme", t);
        localStorage.setItem("vc-theme", t);
      },
    },
  },
});
app.use(router);
app.mount("#app");
