export const auditViewTemplate = `
  <div v-show="tab===5" class="panel">
    <h2>审计与争用</h2>
    <h3>争用</h3>
    <table>
      <thead><tr><th>锁</th><th>人</th><th>动作</th><th>详情</th></tr></thead>
      <tbody>
        <tr v-for="c in contention" :key="c.id">
          <td>{{ c.lock_key }}</td><td>{{ c.actor }}</td><td>{{ c.action }}</td><td>{{ c.detail }}</td>
        </tr>
      </tbody>
    </table>
    <h3>余席（扣待确认）</h3>
    <table>
      <thead><tr><th>档</th><th>容量</th><th>已订</th><th>余席</th><th>态</th></tr></thead>
      <tbody>
        <tr v-for="r in auditRemaining" :key="r.slot_code">
          <td>{{ r.slot_code }}</td><td>{{ r.capacity }}</td><td>{{ r.booked }}</td>
          <td class="num">{{ r.remaining }}</td><td>{{ r.status }}</td>
        </tr>
      </tbody>
    </table>
    <h3>审计</h3>
    <table>
      <thead><tr><th>人</th><th>动作</th><th>目标</th><th>时</th></tr></thead>
      <tbody>
        <tr v-for="a in audits" :key="a.id">
          <td>{{ a.actor }}</td><td>{{ a.action }}</td><td>{{ a.target }}</td><td>{{ a.created_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>
`;
