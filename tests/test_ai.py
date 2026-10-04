import json
import io
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
from ai_service import generate, extract, Budget, AIError, DEFAULT_MODEL, FALLBACK_MODEL
from schedule import COLUMNS

class AITests(unittest.TestCase):
    def test_missing_key_and_invalid_model_never_connect(self):
        with patch('ai_service.urlopen') as network:
            for key,model in [('',DEFAULT_MODEL),('secret','../bad')]:
                with self.assertRaises(AIError): generate(key,model,[],{})
            network.assert_not_called()

    def test_request_and_response(self):
        reply={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"rows": []}'}]}}]}
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps(reply).encode()
        with patch('ai_service.urlopen',return_value=response) as network:
            self.assertEqual(generate('secret',DEFAULT_MODEL,[{'text':'test'}],{}),{'rows':[]})
            request=network.call_args.args[0]
            self.assertNotIn('secret',request.full_url)
            self.assertEqual(network.call_args.kwargs['timeout'],25)

    def test_temporary_failure_recovers_without_duplicate_result(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"ok":true}'}]}}]}).encode()
        with patch('ai_service.urlopen',side_effect=[HTTPError('url',503,'private',{},None),response]) as network, patch('ai_service.time.sleep') as sleep:
            self.assertEqual(generate('secret',DEFAULT_MODEL,[],{}),{'ok':True})
            self.assertEqual(network.call_count,2)
            sleep.assert_called_once()

    def test_temporary_failure_is_bounded_and_bad_request_not_retried(self):
        for code,expected in [(503,3),(400,1),(403,1),(429,1)]:
            with patch('ai_service.urlopen',side_effect=lambda *a,**k: (_ for _ in ()).throw(HTTPError('url',code,'private',{},None))) as network, patch('ai_service.time.sleep'):
                with self.assertRaises(AIError): generate('secret',DEFAULT_MODEL,[],{})
                self.assertEqual(network.call_count,expected)
                if code==503:
                    self.assertIn(FALLBACK_MODEL,network.call_args.args[0].full_url)
                else:
                    self.assertIn(DEFAULT_MODEL,network.call_args.args[0].full_url)

    def test_fallback_keeps_payload_and_returns_real_response(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"title":"SQL"}'}]}}]}).encode()
        failures=[HTTPError('url',503,'private',{},None),HTTPError('url',503,'private',{},None),response]
        with patch('ai_service.urlopen',side_effect=failures) as network, patch('ai_service.time.sleep'):
            self.assertEqual(generate('secret',DEFAULT_MODEL,[{'text':'source'}],{'type':'object'}),{'title':'SQL'})
            requests=[call.args[0] for call in network.call_args_list]
            self.assertIn(DEFAULT_MODEL,requests[0].full_url)
            self.assertIn(FALLBACK_MODEL,requests[2].full_url)
            self.assertEqual(requests[0].data,requests[2].data)

    def test_errors_are_sanitized(self):
        with patch('ai_service.urlopen',side_effect=HTTPError('url',429,'SECRET',{},None)):
            with self.assertRaisesRegex(AIError,'квота'): generate('secret',DEFAULT_MODEL,[],{})

    def test_invalid_key_reason_without_provider_text(self):
        body=json.dumps({'error':{'message':'SECRET','details':[{'reason':'API_KEY_INVALID'}]}}).encode()
        with patch('ai_service.urlopen',side_effect=HTTPError('url',400,'SECRET',{},io.BytesIO(body))):
            with self.assertRaisesRegex(AIError,'Ключ Gemini не принят') as error:
                generate('secret',DEFAULT_MODEL,[],{})
            self.assertNotIn('SECRET',str(error.exception))

    def test_malformed_and_truncated(self):
        for reply in [b'invalid',b'{}',json.dumps({'candidates':[{'finishReason':'MAX_TOKENS'}]}).encode()]:
            response=MagicMock()
            response.__enter__.return_value.read.return_value=reply
            with patch('ai_service.urlopen',return_value=response):
                with self.assertRaises(AIError): generate('secret',DEFAULT_MODEL,[],{})

    def test_upload_and_extraction_validation(self):
        with patch('ai_service.generate') as model:
            with self.assertRaises(AIError): extract('key',DEFAULT_MODEL,b'fake','image/png','X')
            model.assert_not_called()
            model.return_value={'rows':[{c:'' for c in COLUMNS}],'warnings':['Проверьте дату']}
            rows,warnings=extract('key',DEFAULT_MODEL,b'%PDF-test','application/pdf','X')
            self.assertEqual(len(rows),1)
            model.return_value={'rows':[{'subject':12}],'warnings':[]}
            with self.assertRaises(AIError): extract('key',DEFAULT_MODEL,b'%PDF-test','application/pdf','X')

    def test_budget(self):
        budget=Budget()
        for _ in range(100): budget.claim()
        with self.assertRaises(AIError): budget.claim()

if __name__=='__main__': unittest.main()
