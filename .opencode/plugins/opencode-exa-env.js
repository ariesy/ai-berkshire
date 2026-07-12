// .opencode/plugins/opencode-exa-env.js
//
// Enable the built-in websearch tool (Exa AI) for this project.
// Without OPENCODE_ENABLE_EXA=1, the websearch tool is unavailable
// (see https://opencode.ai/docs/tools#websearch).
//
// Loaded automatically from .opencode/plugins/ at OpenCode startup;
// no opencode.json entry needed.
export const OpencodeExaEnv = async () => {
  return {
    "shell.env": async (input, output) => {
      output.env.OPENCODE_ENABLE_EXA = "1"
    },
  }
}