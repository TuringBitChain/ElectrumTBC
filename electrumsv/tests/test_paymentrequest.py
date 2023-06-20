from bitcoinx import Bitcoin, P2PKH_Address

from electrumsv import dpp_messages


PKH_HEX = "8b2b1e60ccf6c206f1fde862897cd61be5f2a021"
PKH_ADDRESS = P2PKH_Address(bytes.fromhex(PKH_HEX), Bitcoin)
P2PKH_SCRIPT = PKH_ADDRESS.to_script()

# TRANSACTION_HEX = ("0100000002f25568d10d46181bc65b01b735f8cccdb91e4e7d172c5efb984b839d1c"+
#     "912084000000002401ff2102faf7f10ccad1bc40e697e6b90b1d7c9daf92fdf47a4cf726f1c0422e473"+
#     "0fe85fefffffff146000000000000f25568d10d46181bc65b01b735f8cccdb91e4e7d172c5efb984b83"+
#     "9d1c912084010000006b483045022100fa8ebdc7cefc407fd1b560fb2e2e5e96e900e94634d96df4fd2"+
#     "84126048746a2022028d91ca132a1a386a67df69a2c5ba216218870c256c163d729f1575f7a8824f541"+
#     "21030c4ee92cd3c174e9aabcdec56ddc6b6d09a7767b563055a10e5406ec48f477eafeffffff01de9e0"+
#     "100000000001976a914428f0dbcc74fc3a999bbaf8bf4600531e155e66b88ac75c50800")


# def _generate_address():
#     pkh_bytes = os.urandom(20)
#     return P2PKH_Address(pkh_bytes, Bitcoin)


# class TestPayment(unittest.TestCase):
#     def test_dict_optional_fields_unused(self):
#         payment = dpp_messages.Payment("merchant_data", "transaction_hex")
#         data = payment.to_dict()
#         self.assertTrue('merchantData' in data)
#         self.assertFalse('memo' in data)

#     def test_dict_optional_fields_used(self):
#         payment = dpp_messages.Payment("merchant_data", "transaction_hex", "memo")
#         data = payment.to_dict()
#         self.assertTrue('merchantData' in data)
#         self.assertTrue('memo' in data)

#     def test_json_restoration_all(self):
#         original = dpp_messages.Payment("merchant_data", "transaction_hex", "memo")
#         json_value = original.to_json()
#         restored = dpp_messages.Payment.from_json(json_value)
#         self.assertEqual(original.merchant_data, restored.merchant_data)
#         self.assertEqual(original.transaction_hex, restored.transaction_hex)
#         self.assertEqual(original.memo, restored.memo)

#     def test_json_restoration_required(self):
#         outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
#         original = dpp_messages.Payment("merchant_data", "transaction_hex")
#         json_value = original.to_json()
#         restored = dpp_messages.Payment.from_json(json_value)
#         self.assertEqual(original.merchant_data, restored.merchant_data)
#         self.assertEqual(original.transaction_hex, restored.transaction_hex)
#         self.assertEqual(original.memo, restored.memo)


# class TestPaymentACK(unittest.TestCase):
#     def test_dict_optional_fields_unused(self):
#         payment = dpp_messages.Payment("merchant_data", "transaction_hex")
#         payment_ack = dpp_messages.PaymentACK(payment)
#         data = payment_ack.to_dict()
#         self.assertTrue('payment' in data)
#         self.assertFalse('memo' in data)

#     def test_dict_optional_fields_used(self):
#         payment = dpp_messages.Payment("merchant_data", "transaction_hex", "memo")
#         payment_ack = dpp_messages.PaymentACK(payment, 'memo')
#         data = payment_ack.to_dict()
#         self.assertTrue('payment' in data)
#         self.assertTrue('memo' in data)

#     def test_json_restoration_all(self):
#         payment = dpp_messages.Payment("merchant_data", "transaction_hex", "memo")
#         original = dpp_messages.PaymentACK(payment)
#         json_value = original.to_json()
#         restored = dpp_messages.PaymentACK.from_json(json_value)
#         self.assertEqual(original.payment.merchant_data, restored.payment.merchant_data)
#         self.assertEqual(original.payment.transaction_hex, restored.payment.transaction_hex)
#         self.assertEqual(original.payment.memo, restored.payment.memo)
#         self.assertEqual(original.memo, restored.memo)

#     def test_json_restoration_required(self):
#         payment = dpp_messages.Payment({}, "transaction_hex")
#         original = dpp_messages.PaymentACK(payment)
#         json_value = original.to_json()
#         restored = dpp_messages.PaymentACK.from_json(json_value)
#         self.assertEqual(original.memo, restored.memo)


# class TestDPPMessages(unittest.TestCase):
    # def test_dict_optional_fields_unused(self):
    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     original = dpp_messages.PaymentTerms(outputs, "1.0")
    #     json_value = original.to_json()
    #     restored = dpp_messages.PaymentTerms.from_json(json_value)
    #     self.assertEqual(len(original.outputs), len(restored.outputs))
    #     self.assertEqual(original.outputs[0].script, restored.outputs[0].script)
    #     self.assertEqual(original.creation_timestamp, restored.creation_timestamp)
    #     self.assertEqual(original.expiration_timestamp, restored.expiration_timestamp)
    #     self.assertEqual(original.memo, restored.memo)
    #     self.assertEqual(original.payment_url, restored.payment_url)
    #     self.assertEqual(original.merchant_data, restored.merchant_data)

    # def test_dict_optional_fields_used(self):
    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     creation_timestamp = int(time.time() + 100)
    #     expiration_timestamp = creation_timestamp + 100
    #     request = dpp_messages.PaymentTerms(
    #         outputs, "1.0", creation_timestamp, expiration_timestamp, "memo", "pay_url",
    #         "merchant_data")
    #     json_value = request.to_json()
    #     data = json.loads(json_value)
    #     self.assertTrue('creationTimestamp' in data)
    #     self.assertTrue('expirationTimestamp' in data)
    #     self.assertTrue('memo' in data)
    #     self.assertTrue('paymentUrl' in data)
    #     self.assertTrue('merchantData' in data)

    # def test_json_restoration_all(self):
    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     creation_timestamp = int(time.time() + 100)
    #     expiration_timestamp = creation_timestamp + 100
    #     original = dpp_messages.PaymentTerms(outputs, "1.0", creation_timestamp,
    #         expiration_timestamp, "memo", "pay_url", "merchant_data")
    #     json_value = original.to_json()
    #     restored = dpp_messages.PaymentTerms.from_json(json_value)
    #     self.assertEqual(len(original.outputs), len(restored.outputs))
    #     self.assertEqual(original.outputs[0].script, restored.outputs[0].script)
    #     self.assertEqual(original.creation_timestamp, restored.creation_timestamp)
    #     self.assertEqual(original.expiration_timestamp, restored.expiration_timestamp)
    #     self.assertEqual(original.memo, restored.memo)
    #     self.assertEqual(original.payment_url, restored.payment_url)
    #     self.assertEqual(original.merchant_data, restored.merchant_data)

    # def test_json_restoration_required(self):
    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     original = dpp_messages.PaymentTerms(outputs, "1.0")
    #     json_value = original.to_json()
    #     restored = dpp_messages.PaymentTerms.from_json(json_value)
    #     self.assertEqual(len(original.outputs), len(restored.outputs))
    #     self.assertEqual(original.outputs[0].script, restored.outputs[0].script)
    #     self.assertEqual(original.creation_timestamp, restored.creation_timestamp)
    #     self.assertEqual(original.expiration_timestamp, restored.expiration_timestamp)
    #     self.assertEqual(original.memo, restored.memo)
    #     self.assertEqual(original.payment_url, restored.payment_url)
    #     self.assertEqual(original.merchant_data, restored.merchant_data)

    # class _FakeRequestResponse:
    #     def __init__(self, status_code, reason, content):
    #         self._status_code = status_code
    #         self._reason = reason
    #         self._content = content

    #     def get_status_code(self):
    #         return self._status_code

    #     def get_reason(self):
    #         return self._reason

    #     def get_content(self):
    #         return self._content

    # @pytest.mark.skip(reason="no way of currently testing this")
    # def test_send_payment_success(self):
    #     payment = dpp_messages.Payment("merchant_data", "transaction_hex")
    #     ack_memo = "ack_memo"
    #     payment_ack = dpp_messages.PaymentACK(payment, ack_memo)
    #     ack_json = payment_ack.to_json()

    #     class PaymentRequestTestable(dpp_messages.PaymentTerms):
    #         def _make_request(self, url, message):
    #             return TestDPPMessages._FakeRequestResponse(200, NotImplemented, ack_json)

    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     creation_timestamp = int(time.time() + 100)
    #     expiration_timestamp = creation_timestamp + 100
    #     payment_request = PaymentRequestTestable(
    #         outputs, creation_timestamp, expiration_timestamp, "memo", "pay_url", "merchant_data")

    #     response_status = payment_request.send_payment(TRANSACTION_HEX)
    #     # The response was successful.
    #     self.assertTrue(response_status)
    #     # The ack memo is the response message.
    #     self.assertEqual(ack_memo, payment_request.error)

    # @pytest.mark.skip(reason="no way of currently testing this")
    # def test_send_payment_ssl_exception(self):
    #     class PaymentRequestTestable(dpp_messages.PaymentTerms):
    #         def _make_request(self, url, message):
    #             return None

    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     creation_timestamp = int(time.time() + 100)
    #     expiration_timestamp = creation_timestamp + 100
    #     payment_request = PaymentRequestTestable(
    #         outputs, creation_timestamp, expiration_timestamp, "memo", "pay_url", "merchant_data")

    #     response_status = payment_request.send_payment(TRANSACTION_HEX)
    #     self.assertFalse(response_status)

    # @pytest.mark.skip(reason="no way of currently testing this")
    # def test_send_payment_default_error(self):
    #     class PaymentRequestTestable(dpp_messages.PaymentTerms):
    #         def _make_request(self, url, message):
    #             return TestDPPMessages._FakeRequestResponse(403, "reason", b"content")

    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     creation_timestamp = int(time.time() + 100)
    #     expiration_timestamp = creation_timestamp + 100
    #     payment_request = PaymentRequestTestable(
    #         outputs, creation_timestamp, expiration_timestamp, "memo", "pay_url", "merchant_data")

    #     response_status = payment_request.send_payment(TRANSACTION_HEX)
    #     self.assertFalse(response_status)
    #     self.assertEqual("reason", payment_request.error)

    # @pytest.mark.skip(reason="no way of currently testing this")
    # def test_send_payment_400_error(self):
    #     class PaymentRequestTestable(dpp_messages.PaymentTerms):
    #         def _make_request(self, url, message):
    #             return TestDPPMessages._FakeRequestResponse(400, "reason", b"content")

    #     outputs = [ dpp_messages.Output(P2PKH_SCRIPT) ]
    #     creation_timestamp = int(time.time() + 100)
    #     expiration_timestamp = creation_timestamp + 100
    #     payment_request = PaymentRequestTestable(
    #         outputs, creation_timestamp, expiration_timestamp, "memo", "pay_url", "merchant_data")

    #     response_status = payment_request.send_payment(TRANSACTION_HEX)
    #     self.assertFalse(response_status)
    #     self.assertEqual("reason: content", payment_request.error)



