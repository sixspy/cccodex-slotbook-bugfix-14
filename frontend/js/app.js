import { createApi } from "./api.js";
import { slotsViewTemplate } from "./views/slots_view.js";
import { holdsViewTemplate } from "./views/holds_view.js";
import { waitlistViewTemplate } from "./views/waitlist_view.js";
import { confirmViewTemplate } from "./views/confirm_view.js";
import { reconcileViewTemplate } from "./views/reconcile_view.js";
import { auditViewTemplate } from "./views/audit_view.js";

const { createApp, ref, onMounted } = Vue;

createApp({
  setup() {
    const token = ref(localStorage.getItem("slotbook_token") || "");
    const user = ref(localStorage.getItem("slotbook_user") || "");
    const username = ref("admin");
    const password = ref("123456");
    const err = ref("");
    const actionErr = ref("");
    const tab = ref(0);
    const nav = ["档期盘", "占位单", "候补队列", "确认入册", "对账互证", "审计争用"];
    const slots = ref([]);
    const holds = ref([]);
    const waitlist = ref([]);
    const bookings = ref([]);
    const recon = ref({});
    const audits = ref([]);
    const auditRemaining = ref([]);
    const contention = ref([]);
    const dash = ref({});
    const holdForm = ref({ slot_code: "S-AM-01", party_key: "P-NEW", seats: 1 });
    const confirmId = ref(1);

    function logout() {
      token.value = "";
      user.value = "";
      localStorage.removeItem("slotbook_token");
      localStorage.removeItem("slotbook_user");
    }
    const api = createApi(() => token.value, logout);

    async function login() {
      err.value = "";
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.value, password: password.value }),
      });
      const j = await r.json();
      if (!r.ok) { err.value = j.detail || "登录失败"; return; }
      token.value = j.token;
      user.value = j.username;
      localStorage.setItem("slotbook_token", j.token);
      localStorage.setItem("slotbook_user", j.username);
      await refresh();
    }

    async function refresh() {
      if (!token.value) return;
      actionErr.value = "";
      dash.value = await api.get("/api/dashboard");
      slots.value = (await api.get("/api/slots")).items;
      holds.value = (await api.get("/api/holds")).items;
      waitlist.value = (await api.get("/api/waitlist")).items;
      bookings.value = (await api.get("/api/bookings")).items;
      recon.value = await api.get("/api/reconcile");
      const auditRes = await api.get("/api/audit");
      audits.value = auditRes.items;
      auditRemaining.value = auditRes.remaining || [];
      contention.value = (await api.get("/api/contention")).items;
    }

    async function doHold() {
      try { actionErr.value = ""; await api.post("/api/holds", holdForm.value); await refresh(); }
      catch (e) { actionErr.value = e.message; }
    }
    async function doConfirm() {
      try { actionErr.value = ""; await api.post("/api/bookings/confirm", { hold_id: confirmId.value }); await refresh(); }
      catch (e) { actionErr.value = e.message; }
    }
    async function promoteWait(id) {
      try { actionErr.value = ""; await api.post("/api/waitlist/promote", { wait_id: id }); await refresh(); }
      catch (e) { actionErr.value = e.message; }
    }

    onMounted(() => { if (token.value) refresh(); });

    return {
      token, user, username, password, err, actionErr, tab, nav,
      slots, holds, waitlist, bookings, recon, audits, auditRemaining, contention, dash,
      holdForm, confirmId, login, logout, refresh, doHold, doConfirm, promoteWait,
    };
  },
  template: `
  <div v-if="!token" class="login">
    <h1>档期预订</h1>
    <p>档期先占位后确认才进正式册</p>
    <div><input v-model="username" placeholder="账号" /></div>
    <div><input v-model="password" type="password" placeholder="密码" /></div>
    <button @click="login">登录</button>
    <p class="err" v-if="err">{{ err }}</p>
  </div>
  <div v-else class="shell">
    <aside class="rail">
      <h1>档期预订</h1>
      <div class="sk">占位 → 确认 → 正式册；冲突进候补</div>
      <ul class="steps">
        <li v-for="(n,i) in nav" :key="n" :class="{on: tab===i}" @click="tab=i">{{ n }}</li>
      </ul>
    </aside>
    <main class="main">
      <div class="topbar">
        <span class="pill">{{ user }}</span>
        <div>
          <button class="ghost" @click="refresh">刷新</button>
          <button class="ghost" @click="logout">退出</button>
        </div>
      </div>
      ${slotsViewTemplate}
      ${holdsViewTemplate}
      ${waitlistViewTemplate}
      ${confirmViewTemplate}
      ${reconcileViewTemplate}
      ${auditViewTemplate}
    </main>
  </div>
  `,
}).mount("#app");
