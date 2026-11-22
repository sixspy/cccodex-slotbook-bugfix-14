export const slotsViewTemplate = `
  <div v-show="tab===0" class="panel">
    <h2>档期盘</h2>
    <div class="dash">
      <div class="cell"><div class="n">{{ dash.slots_open }}</div>开放档</div>
      <div class="cell"><div class="n">{{ dash.holds_open }}</div>占位中</div>
      <div class="cell"><div class="n">{{ dash.bookings }}</div>正式册</div>
      <div class="cell"><div class="n">{{ dash.waitlist }}</div>候补</div>
    </div>
    <table>
      <thead><tr><th>编码</th><th>标题</th><th>容量</th><th>已订</th><th>余席</th><th>态</th><th>代</th></tr></thead>
      <tbody>
        <tr v-for="s in slots" :key="s.id">
          <td>{{ s.code }}</td><td>{{ s.title }}</td>
          <td>{{ s.capacity }}</td><td>{{ s.booked }}</td>
          <td class="num">{{ s.remaining }}</td>
          <td>{{ s.status }}</td><td>{{ s.generation }}</td>
        </tr>
      </tbody>
    </table>
  </div>
`;
