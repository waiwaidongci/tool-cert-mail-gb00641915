import {request, saveFile} from '../api/http.js';
import {session} from './session.js';

const call = (path, body) => request(path, {token:session.token, body});
export const workspace = {
  spec: null,
  datasets: [],
  batches: [],
  async init() { this.spec = await request('/spec'); },
  async refresh() {
    [this.datasets, this.batches] = await Promise.all([call('/datasets'), call('/batches')]);
  },
  getDataset: (id, offset = 0) => call(`/datasets/${id}?offset=${offset}`),
  getBatch: id => call(`/batches/${id}`),
  upload: data => call('/datasets', data),
  invoices: () => call('/documents/invoices'),
  notes: () => call('/documents/notes'),
  start: data => call('/batches', data),
  post: (id, data) => call(`/batches/${id}/post`, data),
  posted: () => call('/posted'),
  report: () => call('/report'),
  audit: () => call('/audit'),
  download: (path, filename) => saveFile(path, session.token, filename),
};
