import React from 'react';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { SemanticServerHit, SemanticToolHit, SemanticAgentHit } from '../hooks/useSemanticSearch';

interface SemanticSearchResultsProps {
  query: string;
  loading: boolean;
  error: string | null;
  servers: SemanticServerHit[];
  tools: SemanticToolHit[];
  agents: SemanticAgentHit[];
}

const formatPercent = (value: number) => `${Math.round(Math.min(value, 1) * 100)}%`;

const SemanticSearchResults: React.FC<SemanticSearchResultsProps> = ({
  query,
  loading,
  error,
  servers,
  tools,
  agents
}) => {
  const hasResults = servers.length > 0 || tools.length > 0 || agents.length > 0;

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
            Semantic Search
          </p>
          <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
            Results for <span className="text-purple-600 dark:text-purple-300">“{query}”</span>
          </h3>
        </div>
        {loading && (
          <div className="inline-flex items-center text-sm text-purple-600 dark:text-purple-300">
            <ArrowPathIcon className="h-5 w-5 animate-spin mr-2" />
            Searching…
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/40 dark:bg-red-900/30 dark:text-red-200">
          {error}
        </div>
      )}

      {!loading && !error && !hasResults && (
        <div className="text-center py-16 border border-dashed border-gray-200 dark:border-gray-700 rounded-xl">
          <p className="text-lg font-medium text-gray-700 dark:text-gray-200 mb-2">
            No semantic matches found
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-xl mx-auto">
            Try refining your query or describing the tools or capabilities you need. Semantic
            search understands natural language — phrases like “servers that handle authentication”
            or “tools for syncing calendars” work great.
          </p>
        </div>
      )}

      {servers.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Matching Servers <span className="text-sm font-normal text-gray-500">({servers.length})</span>
            </h4>
          </div>
          <div
            className="grid"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}
          >
            {servers.map((server) => (
              <div
                key={server.path}
                className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-base font-semibold text-gray-900 dark:text-white">
                      {server.server_name}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-300">{server.path}</p>
                  </div>
                  <span className="inline-flex items-center rounded-full bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-200 px-3 py-1 text-xs font-semibold">
                    {formatPercent(server.relevance_score)} match
                  </span>
                </div>
                <p className="mt-3 text-sm text-gray-600 dark:text-gray-300 line-clamp-3">
                  {server.description || server.match_context || 'No description available.'}
                </p>

                {server.tags?.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {server.tags.slice(0, 6).map((tag) => (
                      <span
                        key={tag}
                        className="px-2.5 py-1 text-xs rounded-full bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {server.matching_tools?.length > 0 && (
                  <div className="mt-4 border-t border-dashed border-gray-200 dark:border-gray-700 pt-3">
                    <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                      Relevant tools
                    </p>
                    <ul className="space-y-2">
                      {server.matching_tools.slice(0, 3).map((tool) => (
                        <li key={tool.tool_name} className="text-sm text-gray-700 dark:text-gray-200">
                          <span className="font-medium text-gray-900 dark:text-white">{tool.tool_name}</span>
                          <span className="mx-2 text-gray-400">•</span>
                          <span className="text-gray-600 dark:text-gray-300">
                            {tool.description || tool.match_context || 'No description'}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {tools.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Matching Tools <span className="text-sm font-normal text-gray-500">({tools.length})</span>
            </h4>
          </div>
          <div className="space-y-3">
            {tools.map((tool) => (
              <div
                key={`${tool.server_path}-${tool.tool_name}`}
                className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">
                    {tool.tool_name}
                    <span className="ml-2 text-xs font-normal text-gray-500 dark:text-gray-400">
                      ({tool.server_name})
                    </span>
                  </p>
                  <p className="text-sm text-gray-600 dark:text-gray-300">
                    {tool.description || tool.match_context || 'No description available.'}
                  </p>
                </div>
                <span className="inline-flex items-center rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-200 px-3 py-1 text-xs font-semibold">
                  {formatPercent(tool.relevance_score)} match
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {agents.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Matching Agents <span className="text-sm font-normal text-gray-500">({agents.length})</span>
            </h4>
          </div>
          <div
            className="grid"
            style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}
          >
            {agents.map((agent) => (
              <div
                key={agent.path}
                className="rounded-2xl border border-cyan-200 dark:border-cyan-900/40 bg-white dark:bg-gray-800 p-5 shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-base font-semibold text-gray-900 dark:text-white">
                      {agent.agent_name}
                    </p>
                    <p className="text-xs uppercase tracking-wide text-gray-400 dark:text-gray-500">
                      {agent.visibility || 'public'}
                    </p>
                  </div>
                  <span className="inline-flex items-center rounded-full bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-200 px-3 py-1 text-xs font-semibold">
                    {formatPercent(agent.relevance_score)} match
                  </span>
                </div>

                <p className="mt-3 text-sm text-gray-600 dark:text-gray-300 line-clamp-3">
                  {agent.description || agent.match_context || 'No description available.'}
                </p>

                {agent.skills?.length > 0 && (
                  <div className="mt-4">
                    <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
                      Key Skills
                    </p>
                    <p className="text-xs text-gray-600 dark:text-gray-300">
                      {agent.skills.slice(0, 4).join(', ')}
                      {agent.skills.length > 4 && '…'}
                    </p>
                  </div>
                )}

                {agent.tags?.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {agent.tags.slice(0, 6).map((tag) => (
                      <span
                        key={tag}
                        className="px-2.5 py-1 text-[11px] rounded-full bg-cyan-50 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-200"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-4 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                  <span className="font-semibold text-cyan-700 dark:text-cyan-200">
                    {agent.trust_level || 'unverified'}
                  </span>
                  <span>{agent.is_enabled ? 'Enabled' : 'Disabled'}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default SemanticSearchResults;
