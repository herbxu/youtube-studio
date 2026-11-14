const path = require('node:path');
module.exports = function runtime(episode) {
  if (!process.env.YOUTUBE_WORKBENCH_ROOT) return episode;
  const bench = path.resolve(process.env.YOUTUBE_WORKBENCH_ROOT);
  const works = path.resolve(process.env.YOUTUBE_WORKS_ROOT || process.cwd());
  for (const [root, namespace] of [[works, 'episodes'], [bench, 'examples']]) {
    if (path.dirname(episode) === path.join(root, namespace)) {
      return path.join(bench, 'runtime', namespace, path.basename(episode));
    }
  }
  return episode;
};
