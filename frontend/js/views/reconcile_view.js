export const reconcileViewTemplate = `
  <div v-show="tab===4" class="panel">
    <h2>对账互证</h2>
    <p :class="recon.all_ok ? 'ok' : 'err'">{{ recon.all_ok ? '全部同源' : '存在分裂' }}</p>
    <p :class="recon.remaining_ok ? 'ok' : 'err'">{{ recon.remaining_ok ? '余席已扣待确认' : '余席漏扣待确认' }}</p>
    <table>
      <thead><tr><th>档</th><th>盘面已订</th><th>正式册席</th><th>待确认</th><th>余席</th><th>结果</th></tr></thead>
      <tbody>
        <tr v-for="i in (recon.items||[])" :key="i.slot_code">
          <td>{{ i.slot_code }}</td><td>{{ i.slot_booked }}</td>
          <td>{{ i.booking_seats }}</td><td>{{ i.pending_seats }}</td>
          <td class="num">{{ i.remaining }}</td>
          <td :class="i.ok?'ok':'err'">{{ i.ok ? '通过' : '分裂' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
`;
