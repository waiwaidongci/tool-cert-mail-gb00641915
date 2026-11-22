import {feedback} from '../components/common/fields.js';
import {empty, metrics, panel} from '../components/common/panels.js';
import {table} from '../components/common/table.js';
import {handler} from '../hooks/action.js';
import {workspace} from '../stores/workspace.js';
import {button, el, p} from '../utils/dom.js';

export async function reportPage() {
  const {spec, batches} = workspace;
  const message = feedback();
  const data = await workspace.report();
  const live = data.live;
  const latestComplete = batches.find(item => item.status === 'complete' && item.has_export);
  const exportBtn = latestComplete && button('下载最新对账 CSV',{class:'quiet',onClick:event=>
    handler(exportBtn,message,()=>workspace.download(`/batches/${latestComplete.id}/export`,
      `${spec.short_name}-${latestComplete.id}.csv`))(event)});

  const postedTable = table([
    {key:'organization',label:'机构'}, {key:'settlement_period',label:'结算期'},
    {key:'invoice_id',label:'发票编号'}, {key:'note_codes',label:'已认领验收单'},
    {key:'amount_yuan',label:'入账金额（元）'}, {key:'basis',label:'配对依据'},
    {label:'入账人/时间',render:row=>`${row.author}`},
  ], data.posted_groups, {caption:'已入账整组（重算保留）', empty:'还没有入账整组。', pageSize:10});

  const liveMetrics = live ? metrics(live.metrics) : null;
  const pending = live ? el('div',{},
    panel('待核整组（最优方案不一致）', table([
      {key:'organization',label:'机构'}, {key:'period',label:'结算期'},
      {key:'invoice_id',label:'发票编号'}, {key:'note_codes',label:'候选验收单'},
      {key:'amount_yuan',label:'金额（元）'}, {key:'option_count',label:'候选配法数'},
      {key:'reason',label:'待核原因'},
    ], live.pending_groups, {caption:'待核整组', empty:'无歧义整组。', pageSize:10})),
    panel('待核发票', table([
      {key:'invoice_id',label:'发票编号'}, {key:'organization',label:'机构'},
      {key:'period',label:'结算期'}, {key:'amount_yuan',label:'金额（元）'},
      {key:'reason',label:'待核原因'},
    ], live.pending_invoices, {caption:'待核发票', empty:'无待核发票。', pageSize:10})),
    panel('待核验收单', table([
      {key:'note_code',label:'验收单'}, {key:'organization',label:'机构'},
      {key:'period',label:'结算期'}, {key:'workshop',label:'车间'},
      {key:'amount_yuan',label:'金额（元）'}, {key:'reason',label:'待核原因'},
    ], live.pending_notes, {caption:'待核验收单', empty:'无待核验收单。', pageSize:10})))
    : panel('待核单据', empty('当前没有待认领单据，所有单据均已入账或尚未导入。'));

  return el('div',{},
    panel(spec.pages[5], p('已入账整组保留配对依据并在重算中原样保留；待核单据实时反映最新计算结果与原因。','subtle'),
      exportBtn, message),
    live && el('section',{}, p(live.headline,'intro-copy'), liveMetrics),
    panel('已入账整组', postedTable),
    pending);
}
