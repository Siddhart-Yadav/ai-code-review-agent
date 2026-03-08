"""
Real PR dataset from freeCodeCamp/freeCodeCamp with ground truth annotations.

Each PR has:
- diff_text: the actual unified diff fetched from GitHub
- metadata: PR number, title, repo, file count
- ground_truth: manually annotated relevance labels for each file
  - relevant_files: files that contain meaningful reviewable code changes
  - noise_files: lock files, minified assets, binary files, generated files
  - high_priority_files: files with security/API/auth-related changes
  - expected_issues: known issue categories an ideal review would flag

Source: https://github.com/freeCodeCamp/freeCodeCamp (merged PRs)
"""

from dataclasses import dataclass, field


@dataclass
class PRGroundTruth:
    """Ground truth annotations for a single PR."""
    pr_number: int
    pr_title: str
    repo: str
    total_files: int
    relevant_files: list[str]
    noise_files: list[str]
    high_priority_files: list[str]
    expected_issue_categories: list[str]
    description: str = ""


# ---------------------------------------------------------------------------
# PR #66214: refactor: move static curriculum data out of redux
# 11 files, 479 lines — Redux refactoring, introduces CurriculumDataService
# ---------------------------------------------------------------------------
PR_66214_DIFF = r"""diff --git a/client/src/redux/action-types.js b/client/src/redux/action-types.js
index ab1023c08da026..c9738fc88dbe7a 100644
--- a/client/src/redux/action-types.js
+++ b/client/src/redux/action-types.js
@@ -37,7 +37,6 @@ export const actionTypes = createTypes(
   'updateDonationFormState',
   'updateUserToken',
   'postChargeProcessing',
-  'updateAllChallengesInfo',
   'updateCardRedirecting',
   ...createAsyncTypes('updateCard'),
   ...createAsyncTypes('fetchUser'),
diff --git a/client/src/redux/actions.ts b/client/src/redux/actions.ts
index abfe07e13aa49e..29df5e643671ca 100644
--- a/client/src/redux/actions.ts
+++ b/client/src/redux/actions.ts
@@ -51,10 +51,6 @@ export const toggleTheme = createAction(actionTypes.toggleTheme);
 export const setTheme = createAction(actionTypes.setTheme);
 export const initializeTheme = createAction(actionTypes.initializeTheme);

-export const updateAllChallengesInfo = createAction(
-  actionTypes.updateAllChallengesInfo
-);
-
 export const postCharge = createAction(actionTypes.postCharge);
 export const postChargeProcessing = createAction(
   actionTypes.postChargeProcessing
diff --git a/client/src/redux/index.js b/client/src/redux/index.js
index 6c106d8449af1d..6caae3a3419a07 100644
--- a/client/src/redux/index.js
+++ b/client/src/redux/index.js
@@ -65,10 +65,6 @@ export const initialState = {
   userFetchState: {
     ...defaultFetchState
   },
-  allChallengesInfo: {
-    challengeNodes: [],
-    certificateNodes: []
-  },
   userProfileFetchState: {
     ...defaultFetchState
   },
@@ -169,10 +165,6 @@ export const reducer = handleActions(
       ...state,
       donationFormState: { ...defaultDonationFormState, error: payload }
     }),
-    [actionTypes.updateAllChallengesInfo]: (state, { payload }) => ({
-      ...state,
-      allChallengesInfo: { ...payload }
-    }),
     [actionTypes.fetchUser]: state => ({
       ...state,
       userFetchState: { ...defaultFetchState }
diff --git a/client/src/redux/selectors.js b/client/src/redux/selectors.js
index c1517c86366d81..5b03e62d8ae365 100644
--- a/client/src/redux/selectors.js
+++ b/client/src/redux/selectors.js
@@ -7,7 +7,7 @@ import {
 import { randomBetween } from '../utils/random-between';
 import { getSessionChallengeData } from '../utils/session-storage';

-import { superBlockStructuresSelector } from '../templates/Introduction/redux';
+import { curriculumData } from '../services/curriculum-data';

 import { ns as MainApp } from './action-types';
 export const savedChallengesSelector = state =>
@@ -122,22 +122,6 @@ export const createUserByNameSelector = username => state => {
 };
 export const userFetchStateSelector = state => state[MainApp].userFetchState;
-export const allChallengesInfoSelector = state =>
-  state[MainApp].allChallengesInfo;
-
-export const needsCurriculumDataSelector = createSelector(
-  allChallengesInfoSelector,
-  superBlockStructuresSelector,
-  (allChallengesInfo, superBlockStructures) => {
-    return (
-      !allChallengesInfo?.challengeNodes?.length ||
-      !Object.keys(superBlockStructures).length
-    );
-  }
-);
-
-export const getSuperBlockStructure = (state, superBlock) =>
-  superBlockStructuresSelector(state)[superBlock];

 export const completedChallengesIdsSelector = createSelector(
   completedChallengesSelector,
@@ -150,21 +134,13 @@ export const completedDailyCodingChallengesIdsSelector = createSelector(
 );

 export const completionStateSelector = createSelector(
-  [
-    allChallengesInfoSelector,
-    completedChallengesIdsSelector,
-    superBlockStructuresSelector,
-    state => state.challenge.challengeMeta
-  ],
-  (
-    allChallengesInfo,
-    completedChallengesIds,
-    superBlockStructures,
-    challengeMeta
-  ) => {
-    const { challengeNodes } = allChallengesInfo;
-
-    const structure = superBlockStructures[challengeMeta.superBlock];
+  [completedChallengesIdsSelector, state => state.challenge.challengeMeta],
+  (completedChallengesIds, challengeMeta) => {
+    const challengeNodes = curriculumData.challengeNodes;
+
+    const structure = curriculumData.getSuperBlockStructure(
+      challengeMeta.superBlock
+    );

     const chapters = structure?.chapters ?? [];
diff --git a/client/src/services/curriculum-data.ts b/client/src/services/curriculum-data.ts
new file mode 100644
index 00000000000000..422c8fd94cfc3a
--- /dev/null
+++ b/client/src/services/curriculum-data.ts
@@ -0,0 +1,57 @@
+import type {
+  ChallengeNode,
+  CertificateNode,
+  SuperBlockStructure
+} from '../redux/prop-types';
+
+class CurriculumDataService {
+  #challengeNodes: ChallengeNode[] = [];
+  #certificateNodes: CertificateNode[] = [];
+  #superBlockStructures: Record<string, SuperBlockStructure> = {};
+
+  initialize(data: {
+    challengeNodes: ChallengeNode[];
+    certificateNodes: CertificateNode[];
+    superBlockStructures: Record<string, SuperBlockStructure>;
+  }): void {
+    this.#challengeNodes = data.challengeNodes;
+    this.#certificateNodes = data.certificateNodes;
+    this.#superBlockStructures = data.superBlockStructures;
+  }
+
+  get hasData(): boolean {
+    return (
+      this.#challengeNodes.length > 0 ||
+      this.#certificateNodes.length > 0 ||
+      Object.keys(this.#superBlockStructures).length > 0
+    );
+  }
+
+  get challengeNodes(): ChallengeNode[] {
+    return this.#challengeNodes;
+  }
+
+  get certificateNodes(): CertificateNode[] {
+    return this.#certificateNodes;
+  }
+
+  get superBlockStructures(): Record<string, SuperBlockStructure> {
+    return this.#superBlockStructures;
+  }
+
+  getSuperBlockStructure(superBlock: string): SuperBlockStructure | undefined {
+    return this.#superBlockStructures[superBlock];
+  }
+}
+
+export const curriculumData = new CurriculumDataService();
diff --git a/client/src/templates/Challenges/redux/execute-challenge-saga.js b/client/src/templates/Challenges/redux/execute-challenge-saga.js
index e028413a45a55d..ef6240df277d16 100644
--- a/client/src/templates/Challenges/redux/execute-challenge-saga.js
+++ b/client/src/templates/Challenges/redux/execute-challenge-saga.js
@@ -54,7 +54,7 @@ import {
   updateLogs,
   updateTests
 } from './actions';
-import { allChallengesInfoSelector } from '../../../redux/selectors';
+import { curriculumData } from '../../../services/curriculum-data';
 import {
   challengeDataSelector,
   challengeMetaSelector,
@@ -142,8 +142,7 @@ export function* executeChallengeSaga({ payload }) {
   const isBlockCompleted = yield select(isBlockNewlyCompletedSelector);
   if (challengeComplete) {
     playTone('tests-completed');
-    const allChallengesInfo = yield select(allChallengesInfoSelector);
-    if (isBlockCompleted && allChallengesInfo?.challengeNodes?.length) {
+    if (isBlockCompleted && curriculumData.hasData) {
       fireConfetti();
     }
   } else {
diff --git a/client/src/templates/Challenges/redux/selectors.js b/client/src/templates/Challenges/redux/selectors.js
index 5f85179e1b2520..45a95ab1c7734e 100644
--- a/client/src/templates/Challenges/redux/selectors.js
+++ b/client/src/templates/Challenges/redux/selectors.js
@@ -2,16 +2,16 @@ import { createSelector } from 'reselect';
 import { challengeTypes } from '@freecodecamp/shared/config/challenge-types';
 import {
   completedChallengesSelector,
-  allChallengesInfoSelector,
   isSignedInSelector,
   completionStateSelector,
   completedChallengesIdsSelector,
   completedDailyCodingChallengesIdsSelector
 } from '../../../redux/selectors';
+import { curriculumData } from '../../../services/curriculum-data';
 import {
-  getCurrentBlockIds,
   getCompletedChallengesInBlock,
-  getCompletedPercentage
+  getCompletedPercentage,
+  getCurrentBlockIds
 } from '../../../utils/get-completion-percentage';
 import { ns } from './action-types';

@@ -120,9 +120,12 @@ export const challengeDataSelector = state => {

 export const currentBlockIdsSelector = createSelector(
   challengeMetaSelector,
-  allChallengesInfoSelector,
-  (challengeMeta, allChallengesInfo) => {
+  challengeMeta => {
     const { block, certification, challengeType } = challengeMeta;
+    const allChallengesInfo = {
+      challengeNodes: curriculumData.challengeNodes,
+      certificateNodes: curriculumData.certificateNodes
+    };
     return getCurrentBlockIds(
       allChallengesInfo,
diff --git a/client/src/templates/Challenges/utils/fetch-all-curriculum-data.tsx b/client/src/templates/Challenges/utils/fetch-all-curriculum-data.tsx
index b0bbf297ffc702..ae60bc57e7cda1 100644
--- a/client/src/templates/Challenges/utils/fetch-all-curriculum-data.tsx
+++ b/client/src/templates/Challenges/utils/fetch-all-curriculum-data.tsx
@@ -1,22 +1,14 @@
-import { useEffect } from 'react';
-import { useDispatch, useSelector } from 'react-redux';
+import { useDispatch } from 'react-redux';
 import { useStaticQuery, graphql } from 'gatsby';
-import { updateAllChallengesInfo } from '../../../redux/actions';
 import { submitChallenge } from '../redux/actions';
-import {
-  updateSuperBlockStructures,
-  superBlockStructuresSelector
-} from '../../../templates/Introduction/redux';
-import {
-  allChallengesInfoSelector,
-  needsCurriculumDataSelector
-} from '../../../redux/selectors';
+import { curriculumData } from '../../../services/curriculum-data';
 import type {
   CertificateNode,
   ChallengeNode,
   SuperBlockStructure
 } from '../../../redux/prop-types';
+import { useEffect } from 'react';

 interface AllCurriculumData {
   allChallengeNode: { nodes: ChallengeNode[] };
@@ -25,15 +17,6 @@ interface AllCurriculumData {
 }

 export function useFetchAllCurriculumData(): void {
-  const dispatch = useDispatch();
-  const needsCurriculumData = useSelector(needsCurriculumDataSelector);
-  const allChallengesInfo = useSelector(allChallengesInfoSelector);
-  const superBlockStructures = useSelector(superBlockStructuresSelector);
-
   const {
     allChallengeNode: { nodes: challengeNodes },
     allCertificateNode: { nodes: certificateNodes },
@@ -82,42 +65,25 @@ export function useFetchAllCurriculumData(): void {
   } `);

+  // Initialize curriculum data
   useEffect(() => {
-    if (!needsCurriculumData) return;
+    const structuresMap: Record<string, SuperBlockStructure> = {};
+    superBlockStructureNodes.forEach(node => {
+      structuresMap[node.superBlock] = node;
+    });

-    if (!allChallengesInfo?.challengeNodes?.length) {
-      dispatch(
-        updateAllChallengesInfo({
-          challengeNodes,
-          certificateNodes
-        })
-      );
-    }
-
-    if (Object.keys(superBlockStructures || {}).length === 0) {
-      const structuresMap: Record<string, SuperBlockStructure> = {};
-      superBlockStructureNodes.forEach(node => {
-        structuresMap[node.superBlock] = node;
-      });
-      dispatch(updateSuperBlockStructures(structuresMap));
-    }
-  }, [
-    dispatch,
-    needsCurriculumData,
-    challengeNodes,
-    certificateNodes,
-    superBlockStructureNodes,
-    allChallengesInfo,
-    superBlockStructures
-  ]);
+    curriculumData.initialize({
+      challengeNodes,
+      certificateNodes,
+      superBlockStructures: structuresMap
+    });
+  }, [challengeNodes, certificateNodes, superBlockStructureNodes]);
 }

 export function useSubmit() {
-  // The submitChallenge epic needs the curriculum data
+  // Ensure curriculum data is loaded before challenge submission
   useFetchAllCurriculumData();
   const dispatch = useDispatch();
diff --git a/client/src/templates/Introduction/redux/index.js b/client/src/templates/Introduction/redux/index.js
index e0aa26f544ff1c..31638ac43af945 100644
--- a/client/src/templates/Introduction/redux/index.js
+++ b/client/src/templates/Introduction/redux/index.js
@@ -7,25 +7,16 @@ export const ns = 'curriculumMap';

 const initialState = {
   expandedState: {
     block: {}
-  },
-  superBlockStructures: {}
+  }
 };

-const types = createTypes(
-  ['resetExpansion', 'toggleBlock', 'updateSuperBlockStructures'],
-  ns
-);
+const types = createTypes(['resetExpansion', 'toggleBlock'], ns);

 export const resetExpansion = createAction(types.resetExpansion);
 export const toggleBlock = createAction(types.toggleBlock);
-export const updateSuperBlockStructures = createAction(
-  types.updateSuperBlockStructures
-);

 export const makeExpandedBlockSelector = block => state =>
   !!state[ns].expandedState.block[block];
-export const superBlockStructuresSelector = state =>
-  state[ns].superBlockStructures || {};

 export const reducer = handleActions(
   {
@@ -44,10 +35,6 @@ export const reducer = handleActions(
           [payload]: !state.expandedState.block[payload]
         }
       }
-    }),
-    [types.updateSuperBlockStructures]: (state, { payload }) => ({
-      ...state,
-      superBlockStructures: { ...payload }
     })
   },
   initialState
"""

PR_66214_GROUND_TRUTH = PRGroundTruth(
    pr_number=66214,
    pr_title="refactor: move static curriculum data out of redux",
    repo="freeCodeCamp/freeCodeCamp",
    total_files=11,
    relevant_files=[
        "client/src/redux/action-types.js",
        "client/src/redux/actions.ts",
        "client/src/redux/index.js",
        "client/src/redux/selectors.js",
        "client/src/services/curriculum-data.ts",
        "client/src/templates/Challenges/redux/execute-challenge-saga.js",
        "client/src/templates/Challenges/redux/selectors.js",
        "client/src/templates/Challenges/utils/fetch-all-curriculum-data.tsx",
        "client/src/templates/Introduction/redux/index.js",
        "client/src/templates/Challenges/components/completion-modal.test.tsx",
        "client/src/templates/Challenges/redux/completion-epic.test.js",
    ],
    noise_files=[],
    high_priority_files=[
        "client/src/services/curriculum-data.ts",
        "client/src/redux/selectors.js",
        "client/src/templates/Challenges/redux/selectors.js",
    ],
    expected_issue_categories=[
        "architecture",
        "state-management",
        "singleton-pattern",
    ],
    description="Large refactor removing curriculum data from Redux store into a singleton service class.",
)


# ---------------------------------------------------------------------------
# PR #66259: feat(client): add tsconfig support to editor and use it in TS challenges
# 18 files, 594 lines — Feature addition: tsconfig.json support in code editor
# ---------------------------------------------------------------------------
PR_66259_DIFF = r"""diff --git a/client/src/templates/Challenges/classic/editor.tsx b/client/src/templates/Challenges/classic/editor.tsx
index e86b0fd8e724cc..bb8b72b4175c0c 100644
--- a/client/src/templates/Challenges/classic/editor.tsx
+++ b/client/src/templates/Challenges/classic/editor.tsx
@@ -213,7 +213,8 @@ const modeMap = {
   ts: 'typescript',
   tsx: 'typescript',
   py: 'python',
-  python: 'python'
+  python: 'python',
+  json: 'json'
 };

 let monacoThemesDefined = false;
@@ -394,6 +395,11 @@ const Editor = (props: EditorProps): JSX.Element => {
       allowUmdGlobalAccess: true
     });

+    // support JSONC:
+    monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
+      allowComments: true
+    });
+
     defineMonacoThemes(monaco, { usesMultifileEditor });
diff --git a/client/src/templates/Challenges/classic/multifile-editor.tsx b/client/src/templates/Challenges/classic/multifile-editor.tsx
index 18c68837425121..84c63e7048145d 100644
--- a/client/src/templates/Challenges/classic/multifile-editor.tsx
+++ b/client/src/templates/Challenges/classic/multifile-editor.tsx
@@ -19,6 +19,7 @@ export type VisibleEditors = {
   indexts?: boolean;
   indextsx?: boolean;
   mainpy?: boolean;
+  tsconfigjson?: boolean;
 };
@@ -72,7 +73,8 @@ const MultifileEditor = (props: MultifileEditorProps) => {
     indexts,
     indexjsx,
     indextsx,
-    mainpy
+    mainpy,
+    tsconfigjson
   },
@@ -102,6 +104,7 @@ const MultifileEditor = (props: MultifileEditorProps) => {
     if (scriptjs) editorKeys.push('scriptjs');
     if (mainpy) editorKeys.push('mainpy');
     if (indexts) editorKeys.push('indexts');
+    if (tsconfigjson) editorKeys.push('tsconfigjson');
diff --git a/client/utils/sort-challengefiles.ts b/client/utils/sort-challengefiles.ts
index 4db2f4d52a94f5..b1bdb1b18f3f30 100644
--- a/client/utils/sort-challengefiles.ts
+++ b/client/utils/sort-challengefiles.ts
@@ -14,6 +14,8 @@ export function sortChallengeFiles<File extends { fileKey: string }>(
     if (b.fileKey === 'scriptjs') return 1;
     if (a.fileKey === 'indexts') return -1;
     if (b.fileKey === 'indexts') return 1;
+    if (a.fileKey === 'tsconfigjson') return -1;
+    if (b.fileKey === 'tsconfigjson') return 1;
     return 0;
   });
 }
diff --git a/packages/challenge-builder/src/build.ts b/packages/challenge-builder/src/build.ts
index 90560260941986..e0012971b7575e 100644
--- a/packages/challenge-builder/src/build.ts
+++ b/packages/challenge-builder/src/build.ts
@@ -8,6 +8,7 @@ import {
   getPythonTransformers,
   getMultifileJSXTransformers
 } from './transformers.js';
+import { setupTSCompiler } from './typescript-worker-handler.js';

 interface Source {
   index: string;
@@ -165,6 +166,39 @@ type BuildResult = {
   error?: unknown;
 };

+function hasTS(challengeFiles: ChallengeFile[]) {
+  return challengeFiles.some(
+    challengeFile => challengeFile.ext === 'ts' || challengeFile.ext === 'tsx'
+  );
+}
+
+const isTSConfig = (f: { name: string; ext: string }) =>
+  f.name === 'tsconfig' && f.ext === 'json';
+
+export function getTSConfig(challengeFiles: ChallengeFile[]) {
+  const tsConfigFiles = challengeFiles.filter(isTSConfig);
+
+  if (tsConfigFiles.length > 1) {
+    throw new Error(
+      'TypeScript challenge must include only one tsconfig.json file'
+    );
+  }
+
+  return tsConfigFiles.length === 1 ? tsConfigFiles[0].contents : null;
+}
+
+async function configureTSCompiler(challengeFiles: ChallengeFile[]) {
+  if (hasTS(challengeFiles)) {
+    const tsConfig = getTSConfig(challengeFiles);
+    if (tsConfig) {
+      await setupTSCompiler(tsConfig);
+    } else {
+      await setupTSCompiler();
+    }
+  }
+}
+
 async function buildDOMChallenge(
@@ -182,12 +216,10 @@ async function buildDOMChallenge(
   const hasJsx = challengeFiles.some(
     challengeFile => challengeFile.ext === 'jsx' || challengeFile.ext === 'tsx'
   );
-  const isMultifile = challengeFiles.length > 1;
-
-  const requiresReact16 = required.some(({ src }) =>
-    src?.includes('https://cdnjs.cloudflare.com/ajax/libs/react/16.')
-  );
+  await configureTSCompiler(challengeFiles);
+  const sourceFiles = challengeFiles.filter(file => !isTSConfig(file));
+  const isMultifile = sourceFiles.length > 1;

   const transformers = (isMultifile && hasJsx
@@ -195,7 +227,7 @@ async function buildDOMChallenge(
     : getTransformers(options));

   const pipeLine = composeFunctions(...transformers);
-  const finalFiles = await Promise.all(challengeFiles.map(pipeLine));
+  const finalFiles = await Promise.all(sourceFiles.map(pipeLine));
diff --git a/packages/challenge-builder/src/build.test.ts b/packages/challenge-builder/src/build.test.ts
new file mode 100644
index 00000000000000..1f09b32737cfd4
--- /dev/null
+++ b/packages/challenge-builder/src/build.test.ts
@@ -0,0 +1,36 @@
+import { describe, expect, it } from 'vitest';
+import { getTSConfig } from './build';
+import { ChallengeFile } from '@freecodecamp/shared/utils/polyvinyl';
+
+describe('getTSConfig', () => {
+  it("should return the tsconfig file's contents if it exists", () => {
+    const compileOptions = 'any string is valid here';
+    const challengeFiles = [
+      { name: 'index', ext: 'ts' },
+      { name: 'tsconfig', ext: 'json', contents: compileOptions }
+    ] as ChallengeFile[];
+    expect(getTSConfig(challengeFiles)).toEqual(compileOptions);
+  });
+
+  it('should return null if there is no tsconfig file', () => {
+    const challengeFiles = [
+      { name: 'index', ext: 'ts' },
+      { name: 'app', ext: 'ts' }
+    ] as ChallengeFile[];
+    expect(getTSConfig(challengeFiles)).toBeNull();
+  });
+
+  it('should throw an error if there are multiple tsconfig.json files', () => {
+    const challengeFiles = [
+      { name: 'index', ext: 'ts' },
+      { name: 'tsconfig', ext: 'json' },
+      { name: 'tsconfig', ext: 'json' }
+    ] as ChallengeFile[];
+    expect(() => getTSConfig(challengeFiles)).toThrow(
+      'TypeScript challenge must include only one tsconfig.json file'
+    );
+  });
+});
diff --git a/packages/challenge-builder/src/transformers.js b/packages/challenge-builder/src/transformers.js
index 034bff8db901fe..5c3c30913bc979 100644
--- a/packages/challenge-builder/src/transformers.js
+++ b/packages/challenge-builder/src/transformers.js
@@ -18,10 +18,7 @@ import {

 import { version } from '@freecodecamp/browser-scripts/package.json';
 import { WorkerExecutor } from './worker-executor';
-import {
-  compileTypeScriptCode,
-  setupTSCompiler
-} from './typescript-worker-handler';
+import { compileTypeScriptCode } from './typescript-worker-handler';

 const protectTimeout = 100;
 const testProtectTimeout = 1500;
@@ -148,7 +145,6 @@ const getJSXModuleTranspiler = loopProtectOptions => async challengeFile => {

 const getTSTranspiler = loopProtectOptions => async challengeFile => {
   await loadBabel();
-  await setupTSCompiler();
   const babelOptions = getBabelOptions(presetsJS, loopProtectOptions);
@@ -159,7 +155,6 @@ const getTSTranspiler = loopProtectOptions => async challengeFile => {
 const getTSXModuleTranspiler = loopProtectOptions => async challengeFile => {
   await loadBabel();
   await loadPresetReact();
-  await setupTSCompiler();
diff --git a/packages/challenge-builder/src/typescript-worker-handler.ts b/packages/challenge-builder/src/typescript-worker-handler.ts
index a255a0850828f9..acfc06447974cd 100644
--- a/packages/challenge-builder/src/typescript-worker-handler.ts
+++ b/packages/challenge-builder/src/typescript-worker-handler.ts
@@ -31,9 +31,7 @@ export function compileTypeScriptCode(code: string): Promise<string> {
   });
 }

-export function setupTSCompiler(
-  compilerOptions?: Record<string, unknown>
-): Promise<boolean> {
+export function setupTSCompiler(compilerOptions?: string): Promise<boolean> {
   return awaitResponse({
     messenger: getTypeScriptWorker(),
     message: { type: 'setup', ...(compilerOptions && { compilerOptions }) },
diff --git a/packages/shared/src/utils/polyvinyl.ts b/packages/shared/src/utils/polyvinyl.ts
index f1f76c4a02f5b2..1e68cc788904b7 100644
--- a/packages/shared/src/utils/polyvinyl.ts
+++ b/packages/shared/src/utils/polyvinyl.ts
@@ -1,4 +1,4 @@
-const exts = ['js', 'html', 'css', 'jsx', 'ts', 'tsx', 'py'] as const;
+const exts = ['js', 'html', 'css', 'jsx', 'ts', 'tsx', 'py', 'json'] as const;
 export type Ext = (typeof exts)[number];
diff --git a/tools/challenge-parser/parser/plugins/utils/get-file-visitor.js b/tools/challenge-parser/parser/plugins/utils/get-file-visitor.js
index 86c2b9a3d10103..aaf0b6f55ad33a 100644
--- a/tools/challenge-parser/parser/plugins/utils/get-file-visitor.js
+++ b/tools/challenge-parser/parser/plugins/utils/get-file-visitor.js
@@ -8,7 +8,16 @@ const keyToSection = {
   head: 'before-user-code',
   tail: 'after-user-code'
 };
-const supportedLanguages = ['js', 'css', 'html', 'jsx', 'py', 'ts', 'tsx'];
+const supportedLanguages = [
+  'js',
+  'css',
+  'html',
+  'jsx',
+  'py',
+  'ts',
+  'tsx',
+  'json'
+];
 const longToShortLanguages = {
   javascript: 'js',
   typescript: 'ts',
@@ -30,7 +39,8 @@ function getFilenames(lang) {
   const langToFilename = {
     js: 'script',
     css: 'styles',
-    py: 'main'
+    py: 'main',
+    json: 'tsconfig'
   };
   return langToFilename[lang] ?? 'index';
 }
diff --git a/tools/client-plugins/browser-scripts/modules/typescript-compiler.ts b/tools/client-plugins/browser-scripts/modules/typescript-compiler.ts
index 1f457295667042..84822bf9830da4 100644
--- a/tools/client-plugins/browser-scripts/modules/typescript-compiler.ts
+++ b/tools/client-plugins/browser-scripts/modules/typescript-compiler.ts
@@ -1,5 +1,6 @@
 import type { VirtualTypeScriptEnvironment } from '@typescript/vfs';
 import type { CompilerHost, CompilerOptions } from 'typescript';
+import { parse } from 'jsonc-parser';

-  async setup(opts?: { useNodeModules?: boolean; compilerOptions?: unknown }) {
+  async setup(opts?: { useNodeModules?: boolean; rawCompilerOptions?: string; }) {
     const ts = this.ts;
     const tsvfs = this.tsvfs;

-    const parsedOptions = ts.convertCompilerOptionsFromJson(
-      opts?.compilerOptions ?? {},
+    const parsedOptions = opts?.rawCompilerOptions
+      ? (parse(opts?.rawCompilerOptions) as unknown)
+      : undefined;
+
+    const validatedOptions = ts.convertCompilerOptionsFromJson(
+      parsedOptions ?? {},
       '/'
     );

-      ...parsedOptions.options
+      ...validatedOptions.options
"""

PR_66259_GROUND_TRUTH = PRGroundTruth(
    pr_number=66259,
    pr_title="feat(client): add tsconfig support to editor and use it in TS challenges",
    repo="freeCodeCamp/freeCodeCamp",
    total_files=18,
    relevant_files=[
        "client/src/templates/Challenges/classic/editor.tsx",
        "client/src/templates/Challenges/classic/multifile-editor.tsx",
        "client/utils/sort-challengefiles.ts",
        "client/utils/sort-challengefiles.test.ts",
        "client/utils/__fixtures__/challenges.ts",
        "packages/challenge-builder/src/build.ts",
        "packages/challenge-builder/src/build.test.ts",
        "packages/challenge-builder/src/transformers.js",
        "packages/challenge-builder/src/typescript-worker-handler.ts",
        "packages/shared/src/utils/polyvinyl.ts",
        "tools/challenge-parser/parser/plugins/utils/get-file-visitor.js",
        "tools/challenge-parser/parser/plugins/add-seed.test.js",
        "tools/challenge-parser/parser/__fixtures__/simple.md",
        "tools/client-plugins/browser-scripts/modules/typescript-compiler.ts",
        "tools/client-plugins/browser-scripts/typescript-worker.ts",
        "tools/client-plugins/browser-scripts/package.json",
    ],
    noise_files=[
        "tools/challenge-parser/parser/__snapshots__/index.acceptance.test.js.snap",
        "tools/challenge-parser/parser/plugins/__snapshots__/add-seed.test.js.snap",
    ],
    high_priority_files=[
        "packages/challenge-builder/src/build.ts",
        "packages/challenge-builder/src/typescript-worker-handler.ts",
        "tools/client-plugins/browser-scripts/modules/typescript-compiler.ts",
    ],
    expected_issue_categories=[
        "feature-addition",
        "type-safety",
        "build-system",
        "compiler-config",
    ],
    description="Adds tsconfig.json support to the Monaco editor for TS challenges.",
)


# ---------------------------------------------------------------------------
# PR #66276: fix(client): daily challenge solution downloads as challenge
# 1 file, 21 lines — Small bug fix
# ---------------------------------------------------------------------------
PR_66276_DIFF = r"""diff --git a/client/src/client-only-routes/show-daily-coding-challenge.tsx b/client/src/client-only-routes/show-daily-coding-challenge.tsx
index 698ff63bbb655b..b14810ad2846cb 100644
--- a/client/src/client-only-routes/show-daily-coding-challenge.tsx
+++ b/client/src/client-only-routes/show-daily-coding-challenge.tsx
@@ -46,6 +46,7 @@ function formatChallengeData({
   id,
   challengeNumber,
   title,
+  dashedName: `challenge-${challengeNumber}`,
   description: formatDescription(description),
   superBlock: 'daily-coding-challenge',
   block: 'daily-coding-challenge',
@@ -65,6 +66,7 @@ function formatChallengeData({
 const pageContext = {
   challengeMeta: {
     id,
+    dashedName: `challenge-${challengeNumber}`,
     superBlock: 'daily-coding-challenge',
     block: 'daily-coding-challenge',
     disableLoopProtectTests: true,
"""

PR_66276_GROUND_TRUTH = PRGroundTruth(
    pr_number=66276,
    pr_title="fix(client): daily challenge solution downloads as challenge",
    repo="freeCodeCamp/freeCodeCamp",
    total_files=1,
    relevant_files=[
        "client/src/client-only-routes/show-daily-coding-challenge.tsx",
    ],
    noise_files=[],
    high_priority_files=[
        "client/src/client-only-routes/show-daily-coding-challenge.tsx",
    ],
    expected_issue_categories=["bug-fix", "data-formatting"],
    description="Adds missing dashedName field for daily challenge downloads.",
)


# ---------------------------------------------------------------------------
# PR #66263: fix(deps): update dependency @aws-sdk/client-ses to v3.1000.0
# 2 files, 66 lines — Dependency update with lock file noise
# ---------------------------------------------------------------------------
PR_66263_DIFF = r"""diff --git a/api/package.json b/api/package.json
index 2828f3f2ce6417..8607acb5edb273 100644
--- a/api/package.json
+++ b/api/package.json
@@ -4,7 +4,7 @@
   "url": "https://github.com/freeCodeCamp/freeCodeCamp/issues"
   },
   "dependencies": {
-    "@aws-sdk/client-ses": "3.998.0",
+    "@aws-sdk/client-ses": "3.1000.0",
     "@fastify/accepts": "5.0.4",
     "@fastify/cookie": "11.0.2",
     "@fastify/csrf-protection": "7.1.0",
diff --git a/pnpm-lock.yaml b/pnpm-lock.yaml
index 4d8c76b187698f..0669381d201e9f 100644
--- a/pnpm-lock.yaml
+++ b/pnpm-lock.yaml
@@ -87,8 +87,8 @@ importers:
   api:
     dependencies:
       '@aws-sdk/client-ses':
-        specifier: 3.998.0
-        version: 3.998.0
+        specifier: 3.1000.0
+        version: 3.1000.0
       '@fastify/accepts':
         specifier: 5.0.4
         version: 5.0.4
@@ -1351,8 +1351,8 @@ packages:
   resolution: {integrity: sha512-UomYWcCpM7OZUt1BDlY3guO6mnA4VXzMkNjFbVtWibKQkk4LhcIUXb6SxWSw/gujIrlOZywldjyj8bL6V374IQ==}
   engines: {node: '>=14.0.0'}

-  '@aws-sdk/client-ses@3.998.0':
-    resolution: {integrity: sha512-98PbrNBPVyfFLGDazNeCmmSvEWr3ijiT0lR8SpzStfPKihQ8BIKQWja36Ma2Wgv2TbkKsoGpuPSrrONP3RM6pQ==}
+  '@aws-sdk/client-ses@3.1000.0':
+    resolution: {integrity: sha512-JCNw8ep18XHFdSQ1PBAeWnFWBdsrgCq0sdJILlikpBJ6skd3hg3GwHb0yPgG/wxiahAXDvl8z+kpnWTn7Kb/aQ==}
   engines: {node: '>=20.0.0'}

-  '@aws-sdk/util-locate-window@3.965.4':
-    resolution: {integrity: sha512-H1onv5SkgPBK2P6JR2MjGgbOnttoNzSPIRoeZTNPZYyaplwGg50zS3amXvXqF0/qfXpWEC9rLWU564QTB9bSog==}
-    engines: {node: '>=20.0.0'}
-
   '@aws-sdk/util-locate-window@3.965.5':
     resolution: {integrity: sha512-WhlJNNINQB+9qtLtZJcpQdgZw3SCDCpXdUJP7cToGwHbCWCnRckGlc6Bx/OhWwIYFNAn+FIydY8SZ0QmVu3xTQ==}
     engines: {node: '>=20.0.0'}
"""

PR_66263_GROUND_TRUTH = PRGroundTruth(
    pr_number=66263,
    pr_title="fix(deps): update dependency @aws-sdk/client-ses to v3.1000.0",
    repo="freeCodeCamp/freeCodeCamp",
    total_files=2,
    relevant_files=["api/package.json"],
    noise_files=["pnpm-lock.yaml"],
    high_priority_files=[],
    expected_issue_categories=["dependency-update"],
    description="Bumps @aws-sdk/client-ses from 3.998.0 to 3.1000.0 with lock file changes.",
)


# ---------------------------------------------------------------------------
# Aggregated dataset
# ---------------------------------------------------------------------------
ALL_PRS = [
    (PR_66214_DIFF, PR_66214_GROUND_TRUTH),
    (PR_66259_DIFF, PR_66259_GROUND_TRUTH),
    (PR_66276_DIFF, PR_66276_GROUND_TRUTH),
    (PR_66263_DIFF, PR_66263_GROUND_TRUTH),
]


def get_dataset() -> list[tuple[str, PRGroundTruth]]:
    """Return list of (diff_text, ground_truth) tuples."""
    return ALL_PRS
