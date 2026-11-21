export const waitlistViewTemplate = `
  <div v-show="tab===2" class="panel">
    <h2>候补队列</h2>
    <p class="err" v-if="actionErr">{{ actionErr }}</p>
    <table>
      <thead><tr><th>ID</th><th>档</th><th>当事人</th><th>席</th><th>原因</th><th>态</th><th></th></tr></thead>
      <tbody>
        <tr v-for="w in waitlist" :key="w.id">
          <td>{{ w.id }}</td><td>{{ w.slot_code }}</td><td>{{ w.party_key }}</td>
          <td>{{ w.seats }}</td><td>{{ w.reason }}</td><td>{{ w.status }}</td>
          <td><button class="ghost" v-if="w.status==='候补中'" @click="promoteWait(w.id)">晋升占位</button></td>
        </tr>
      </tbody>
    </table>
  </div>
`;
