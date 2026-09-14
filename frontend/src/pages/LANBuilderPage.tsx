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
  const [subnet, setSubnet] = useState('10.20.0.0/24');
  const [submitting, setSubmitting] = useState(false);

  const valid =
    name.trim().length >= 1 && hostCount >= 1 && subnet.includes('/');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || submitting) return;
    setSubmitting(true);
    try {
      const project = await createProject({
        name: name.trim(),
        topology_type: topology,
        host_count: hostCount,
        subnet: subnet.trim(),
      });
      if (project) {
        pushToast({
          kind: 'success',
          title: 'Project created',
          message: `${project.name} — hit Start to bring up containers.`,
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
          <label className="block text-xs uppercase tracking-wider text-muted mb-2">
            Subnet (CIDR)
          </label>
          <input
            type="text"
            value={subnet}
            onChange={(e) => setSubnet(e.target.value)}
            placeholder="10.20.0.0/24"
            className="w-full bg-bg border border-border rounded-md px-3 py-2 text-text font-mono placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <p className="text-xs text-muted mt-1">
            The /24 subnet fits up to 254 hosts. Pick something unique to avoid
            clashes with other Docker networks.
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
