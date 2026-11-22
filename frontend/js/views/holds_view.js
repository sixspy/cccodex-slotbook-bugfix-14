export const holdsViewTemplate = `
  <div v-show="tab===1" class="panel">
    <h2>占位</h2>
    <div>
      <input v-model="holdForm.slot_code" placeholder="档期编码" />
      <input v-model="holdForm.party_key" placeholder="当事人" />
      <input v-model.number="holdForm.seats" type="number" min="1" style="width:5rem" />
      <button @click="doHold">占位</button>
    </div>
    <p class="err" v-if="actionErr">{{ actionErr }}</p>
    <table>
      <thead><tr><th>ID</th><th>档</th><th>当事人</th><th>席</th><th>余席</th><th>态</th><th>过期</th></tr></thead>
      <tbody>
        <tr v-for="h in holds" :key="h.id">
          <td>{{ h.id }}</td><td>{{ h.slot_code }}</td><td>{{ h.party_key }}</td>
          <td>{{ h.seats }}</td><td class="num">{{ h.remaining }}</td>
          <td>{{ h.status }}</td><td>{{ h.expire_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
`;
