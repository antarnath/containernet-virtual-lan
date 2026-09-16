// LAN Builder — the entry point where users describe the LAN they want.
// Submitting takes them to the project's topology view.

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useProjectStore } from '../store/projectStore';
import { useToastStore } from '../store/toastStore';
import {
  TOPOLOGY_DESCRIPTIONS,
  TOPOLOGY_TYPES,
  TopologyIcon,
} from '../utils/topologyIcons';
import type { TopologyType } from '../types';

export default function LANBuilderPage() {
  const navigate = useNavigate();
  const createProject = useProjectStore((s) => s.createProject);
  const pushToast = useToastStore((s) => s.push);

  const [name, setName] = useState('');
  const [topology, setTopology] = useState<TopologyType>('mesh');
  const [hostCount, setHostCount] = useState(5);
  // Auto-assign is on by default so two consecutive projects never collide
  // on the same Docker bridge subnet. Power users can toggle it off and
  // pick a /24 themselves.
  const [autoSubnet, setAutoSubnet] = useState(true);
  const [subnet, setSubnet] = useState('10.20.0.0/24');
  const [submitting, setSubmitting] = useState(false);

  // Validation: when auto-assigning we don't care what the field says; when
  // not, the subnet must look like CIDR (e.g. "10.20.0.0/24").
  const valid =
    name.trim().length >= 1 &&
    hostCount >= 1 &&
    (autoSubnet || subnet.includes('/'));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    try {
      const project = await createProject({
        name: name.trim(),
        topology_type: topology,
        host_count: hostCount,
        // When auto-assigning, send the flag (and skip the field) so the
        // backend hands out a unique /24 from its allocation pool. Without
        // the flag, a manually-typed subnet still wins and the backend
        // returns 409 on collision so the user can retry with auto on.
        ...(autoSubnet
          ? { assign_subnet_automatically: true }
          : { subnet: subnet.trim() }),
      });
      if (project) {
        pushToast({
          kind: 'success',
          title: 'Project created',
          message:
            `${project.name} — subnet ${project.subnet}. ` +
            'Hit Start to bring up containers.',
        });
        navigate(`/projects/${project.id}/topology`);
      }
    } catch (e) {
      pushToast({
        kind: 'error',
        title: 'Could not create project',
        message: (e as Error).message,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text">LAN Builder</h1>
        <p className="text-sm text-muted mt-1">
          Describe the virtual LAN you want. The backend will generate the
          topology, then you can hit <span className="text-accent">Start</span>
          {' '}to spin up real containers.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="bg-panel border border-border rounded-xl p-6 space-y-6"
      >
        {/* Project name */}
        <div>
          <label className="block text-xs uppercase tracking-wider text-muted mb-2">
            Project Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Lab A — Star Topology"
            className="w-full bg-bg border border-border rounded-md px-3 py-2 text-text placeholder:text-muted focus:border-accent focus:outline-none"
            maxLength={100}
          />
        </div>

        {/* Topology selector */}
        <div>
          <label className="block text-xs uppercase tracking-wider text-muted mb-2">
            Topology Type
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {TOPOLOGY_TYPES.map((t) => {
              const selected = topology === t;
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTopology(t)}
                  className={`flex flex-col items-center gap-2 p-3 rounded-lg border transition-colors ${
                    selected
                      ? 'border-accent bg-accent/10 text-text'
                      : 'border-border bg-bg text-muted hover:border-accent/50 hover:text-text'
                  }`}
                >
                  <TopologyIcon type={t} className="w-10 h-10" />
                  <span className="text-xs uppercase tracking-wider font-medium">
                    {t}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-xs text-muted mt-2">
            {TOPOLOGY_DESCRIPTIONS[topology]}
          </p>
        </div>

        {/* Host count */}
        <div>
          <label className="flex items-center justify-between text-xs uppercase tracking-wider text-muted mb-2">
            <span>Host Count</span>
            <span className="text-accent font-mono text-sm normal-case">
              {hostCount} {hostCount === 1 ? 'host' : 'hosts'}
            </span>
          </label>
          <input
            type="range"
            min={1}
            max={32}
            value={hostCount}
            onChange={(e) => setHostCount(parseInt(e.target.value, 10))}
            className="w-full accent-accent"
          />
          <div className="flex justify-between text-[10px] text-muted mt-1">
            <span>1</span>
            <span>32</span>
          </div>
        </div>

        {/* Subnet */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-xs uppercase tracking-wider text-muted">
              Subnet (CIDR)
            </label>
            <label className="flex items-center gap-2 text-xs text-muted cursor-pointer hover:text-text">
              <input
                type="checkbox"
                checked={autoSubnet}
                onChange={(e) => setAutoSubnet(e.target.checked)}
                className="accent-accent"
              />
              Auto-assign a unique /24
            </label>
          </div>
          <input
            type="text"
            value={subnet}
            onChange={(e) => setSubnet(e.target.value)}
            disabled={autoSubnet}
            placeholder={autoSubnet ? 'auto — backend will pick' : '10.20.0.0/24'}
            className="w-full bg-bg border border-border rounded-md px-3 py-2 text-text font-mono placeholder:text-muted focus:border-accent focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <p className="text-xs text-muted mt-1">
            {autoSubnet
              ? 'The backend will hand out the next free /24 in 10.30.0.0/24 .. 10.99.0.0/24 so this project won’t collide with anything else on the host.'
              : 'Pick a /24 (up to 254 hosts). Must be unique across your projects — collisions return a 409 with a clear message.'}
          </p>
        </div>

        {/* Submit */}
        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={() => navigate('/projects')}
            className="text-sm text-muted hover:text-text"
          >
            ← Cancel
          </button>
          <button
            type="submit"
            disabled={!valid || submitting}
            className="bg-accent text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Creating…' : 'Create Project'}
          </button>
        </div>
      </form>
    </div>
  );
}
