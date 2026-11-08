import copy
import tempfile
import unittest
from pathlib import Path
from autolex.common import WorkflowError, read_json, write_json
from autolex.quality import robustness
from autolex.workflow import Workflow
from autolex.presentation import render_report


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.evidence = {'pages': [{'url': 'https://example.com/a', 'result': {'main_text': 'Original evidence'}}]}
        self.output = {'items': [{'url': 'https://example.com/a', 'title': 'A', 'summary': 'A summary'}]}

    def test_stale_summaries_cannot_pass_missing_evidence(self):
        def executor(work):
            write_json(work/'output.json', self.output)
            return {'returncode': 0, 'log': '', 'timeout': False}
        report = robustness('pass', self.evidence, self.output, self.root/'checks', executor)
        self.assertEqual([c['passed'] for c in report['checks']], [True, True, False, False, False, True, False, False])

    def test_explicit_refusal_is_valid_without_output(self):
        def executor(work):
            pages = read_json(work/'input.json')['pages']
            if len(pages) != 1 or ' '.join(pages[0]['result']['main_text'].split()) != 'Original evidence':
                return {'returncode': 1, 'log': 'Missing evidence', 'timeout': False}
            write_json(work/'output.json', self.output)
            return {'returncode': 0, 'log': '', 'timeout': False}
        self.assertTrue(robustness('pass', self.evidence, self.output, self.root/'checks', executor)['passed'])

    def test_unexpected_crash_is_not_evidence_refusal(self):
        from autolex.quality import evidence_refusal
        for code, log in [(1, 'NameError: missing_evidence is not defined'), (137, 'Missing evidence'), (1, ''), (1, 'IndexError: list index out of range')]:
            with self.subTest(code=code, log=log):
                self.assertFalse(evidence_refusal({'returncode':code,'log':log,'timeout':False},self.root))
        self.assertTrue(evidence_refusal({'returncode':2,'log':'EVIDENCE_ERROR: no matching quotes','timeout':False},self.root))

    def test_timeout_is_not_valid_refusal(self):
        report = robustness('pass', self.evidence, self.output, self.root/'checks',
                            lambda work: {'returncode': -1, 'log': '', 'timeout': True})
        self.assertFalse(any(c['passed'] for c in report['checks']))

    def test_checks_do_not_mutate_source_evidence(self):
        original = copy.deepcopy(self.evidence)
        robustness('pass', self.evidence, self.output, self.root/'checks',
                   lambda work: {'returncode': 1, 'log': '', 'timeout': False})
        self.assertEqual(original, self.evidence)

    def test_brief_persists_and_changed_brief_is_rejected(self):
        Workflow(self.root, 'https://example.com', demo=True, brief='CSV').run('ideas')
        Workflow(self.root, 'https://example.com', demo=True).run()
        self.assertEqual(read_json(self.root/'spec.json')['brief'], 'CSV')
        with self.assertRaisesRegex(WorkflowError, 'brief changed'):
            Workflow(self.root, 'https://example.com', demo=True, brief='Git').run()

    def test_explicit_corpus_survives_model_omission(self):
        Workflow(self.root, 'https://example.com', demo=True,
                 brief='仅使用 https://example.com/a#one 与 https://example.com/b 。6条要点、3条结论').run('ideas')
        spec = read_json(self.root/'spec.json')
        self.assertEqual(spec['selected']['source_urls'], ['https://example.com/a', 'https://example.com/b'])
        self.assertEqual(spec['selected']['source_sections'], ['https://example.com/a#one', 'https://example.com/b'])

    def test_explicit_brief_prevents_invented_acceptance_requirements(self):
        brief='6条中文要点、2条结论；说明恢复边界，不额外规定具体命令数量。'
        Workflow(self.root, 'https://example.com', demo=True, brief=brief).run('ideas')
        spec=read_json(self.root/'spec.json')
        self.assertEqual(spec['acceptance_authority'],'brief')
        self.assertEqual(spec['selected']['acceptance'],brief)

    def test_brief_binding_does_not_mutate_revision_checkpoint(self):
        parent=self.root/'parent'
        Workflow(parent, 'https://example.com', demo=True).run('ideas')
        selected=read_json(parent/'spec.json')['selected']
        revision={'parent':'parent','selected':selected,'feedback':'Keep original scope'}
        before=copy.deepcopy(revision);brief='4条要点、2条结论'
        child=self.root/'child'
        Workflow(child,'https://example.com',demo=True,brief=brief,revision=revision).run('ideas')
        self.assertEqual(revision,before)
        self.assertEqual(Workflow(child,'https://example.com',demo=True,brief=brief,revision=revision).run()['status'],'ready')

    def test_revision_retains_task_and_feedback(self):
        first = self.root/'first'
        Workflow(first, 'https://example.com', demo=True).run()
        selected = read_json(first/'spec.json')['selected']
        revision = {'parent': 'first', 'selected': selected, 'feedback': 'Make quotes readable'}
        second = self.root/'second'
        Workflow(second, 'https://example.com', demo=True, revision=revision).run()
        spec = read_json(second/'spec.json')
        self.assertEqual(spec['selected'], selected)
        self.assertEqual(spec['revision']['feedback'], 'Make quotes readable')
        self.assertIn('index.html', read_json(second/'manifest.json'))

    def test_count_ranges_and_minimums_are_not_treated_as_exact_counts(self):
        from autolex.quality import count_bounds
        self.assertEqual(count_bounds('至少 4 条要点','要点'),(4,None))
        self.assertEqual(count_bounds('最多 6 条要点','要点'),(0,6))
        self.assertEqual(count_bounds('2-3 条结论','结论'),(2,3))
        self.assertIsNone(count_bounds('说明使用场景并给出结论','结论'))

    def test_counts_are_total_across_pages_and_exact_counts_are_enforced(self):
        from autolex.quality import acceptance_metrics
        output = {'items':[{'summary':'中文摘要','points':[{'summary':'证据'}]*3}]*2,
                  'conclusions':[{'text':'中文结论'}]*2}
        metrics, failures = acceptance_metrics(output, '4-6 条要点，2 条结论')
        self.assertEqual(metrics['points_total'], 6)
        self.assertFalse(failures)
        _, failures = acceptance_metrics(output, '产出 5 条带原文引用的要点，2 条结论')
        self.assertEqual(len(failures), 1)
        self.assertIn('exactly 5', failures[0])

    def test_overlong_quote_feedback_is_counted_and_source_bound(self):
        from autolex.quality import quotation_hints
        quote = ' '.join('word'+str(n) for n in range(30))
        evidence = {'pages':[{'url':'https://example.com','result':{'main_text':'Prefix '+quote+' suffix'}}]}
        hints = quotation_hints('quote = '+repr(quote), evidence)
        self.assertEqual(len(hints),1)
        self.assertEqual(hints[0]['word_count'],30)
        for field in ['prefix_25_words','suffix_25_words']:
            self.assertEqual(len(hints[0][field].split()),25)
            self.assertIn(hints[0][field],evidence['pages'][0]['result']['main_text'])
        self.assertFalse(quotation_hints('quote = '+repr(quote+' invented'), evidence))

    def test_quote_repair_hints_include_nearby_option_heading(self):
        from autolex.quality import quotation_hints
        quote='all untracked files are also stashed'
        evidence={'pages':[{'url':'https://example.com','result':{'main_text':'-u --include-untracked '+quote}}]}
        hints=quotation_hints('quote = '+repr(quote),evidence)
        self.assertIn('--include-untracked',hints[0]['source_context'])
        self.assertEqual(hints[0]['word_count'],6)

    def test_original_brief_overrides_model_reduced_count(self):
        from autolex.quality import acceptance_metrics, count_bounds
        output = {'items': [{'points': [{}] * 6}], 'conclusions': [{}] * 2}
        _, failures = acceptance_metrics(output, '6条要点、2条结论', '6条带英文引用的中文要点、3条基于要点的结论')
        self.assertEqual(len(failures), 1)
        self.assertIn('exactly 3', failures[0])
        output['conclusions'].append({})
        self.assertFalse(acceptance_metrics(output, '6条要点、2条结论', '6条要点、3条结论')[1])
        self.assertEqual(count_bounds('4条要点、2条结论', '结论'), (2, 2))

    def test_each_required_source_is_removed_and_emptied(self):
        evidence = copy.deepcopy(self.evidence)
        evidence['pages'].append({'url': 'https://example.com/b', 'result': {'main_text': 'B'}})
        seen = {}
        def executor(work):
            seen[work.parent.name.rsplit('-', 1)[0]] = read_json(work/'input.json')
            return {'returncode': 2, 'log': 'EVIDENCE_ERROR: fixture', 'timeout': False}
        robustness('pass', evidence, self.output, self.root/'checks', executor)
        self.assertEqual([p['url'] for p in seen['missing_source_1']['pages']], ['https://example.com/b'])
        self.assertEqual([p['url'] for p in seen['missing_source_2']['pages']], ['https://example.com/a'])
        self.assertEqual(seen['empty_source_2']['pages'][1]['result']['main_text'], '')
        self.assertEqual(len(seen['duplicate_source']['pages']), 3)
        self.assertEqual(' '.join(seen['equivalent_whitespace']['pages'][0]['result']['main_text'].split()), 'Original evidence')

    def test_invalid_generated_syntax_is_repaired_and_recorded(self):
        from autolex.demo import DemoModel, CODE
        class Model(DemoModel):
            def ask(self, task, context):
                self.calls += 1
                return {'code': 'def broken syntax' if self.calls == 1 else CODE}
        workflow = Workflow(self.root, 'https://example.com', demo=True, model=Model())
        self.assertEqual(workflow.generate_code({}), CODE)
        self.assertIn('line 1', read_json(self.root/'generation-errors-build.json')[0]['error'])

    def test_unchanged_live_repair_is_rejected_before_reexecution(self):
        from autolex.demo import DemoModel
        class Model(DemoModel):
            def ask(self, task, context):
                self.calls += 1
                return {'code': 'pass' if self.calls == 1 else 'print("changed")'}
        workflow = Workflow(self.root, 'https://example.com', model=Model())
        self.assertEqual(workflow.generate_code({'code': 'pass', 'failures': ['missing output']}), 'print("changed")')
        self.assertIn('unchanged code', read_json(self.root/'generation-errors-build.json')[0]['error'])

    def test_inconsistent_review_retries_judge_without_rewriting_code(self):
        class Model:
            calls=0
            def ask(inner,task,context):
                inner.calls+=1
                return {'passed':True,'checks':[{'requirement':'No database writes','passed':inner.calls>1,'reason':'No database access exists'}],'issues':[]}
        model=Model();workflow=Workflow(self.root,'https://example.com',model=model)
        self.assertTrue(workflow.review_output({'output':{}})['passed'])
        self.assertEqual(model.calls,2)
        self.assertEqual(len(read_json(self.root/'review-errors.json')),1)

    def test_rule_quote_failure_is_repaired_with_exact_evidence(self):
        from autolex.demo import DemoModel
        class Model(DemoModel):
            def ask(self, task, context):
                value = super().ask(task, context)
                if task.startswith('RULES') and self.calls == 1:
                    value['requirements'][0]['quote'] = 'invented requirement'
                return value
        state = Workflow(self.root, 'https://example.com', demo=True, model=Model()).run()
        self.assertEqual(state['status'], 'ready')
        self.assertEqual(len(read_json(self.root/'rule-errors.json')), 1)

    def test_report_escapes_source_and_refuses_executable_links(self):
        Workflow(self.root, 'https://example.com', demo=True).run()
        output = read_json(self.root/'output.json')
        output['items'][0].update(title='<script>alert(1)</script>', url='javascript:alert(1)')
        write_json(self.root/'output.json', output)
        report = render_report(self.root, ['main.py'])
        self.assertIn('&lt;script&gt;', report)
        self.assertNotIn('<script>', report)
        self.assertNotIn('href="javascript:', report)
        self.assertIn('main.py', report)


if __name__ == '__main__':
    unittest.main()
