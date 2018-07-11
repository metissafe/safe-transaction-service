import logging
import json
from random import randint

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..serializers import SafeMultisigTransactionSerializer
from ..models import MultisigTransaction, MultisigConfirmation
from .safe_test_case import TestCaseWithSafeContractMixin
from .factories import MultisigTransactionFactory, MultisigTransactionConfirmationFactory


logger = logging.getLogger(__name__)


class TestViews(APITestCase, TestCaseWithSafeContractMixin):

    CALL = 0
    WITHDRAW_AMOUNT = 50000000000000000

    @classmethod
    def setUpTestData(cls):
        cls.prepare_safe_tests()

    def test_about(self):
        request = self.client.get(reverse('v1:about'))
        self.assertEqual(request.status_code, status.HTTP_200_OK)

    def test_multisig_transaction_creation_flow(self):
        w3 = self.w3
        safe_nonce = randint(0, 10)

        logger.info("Test Safe Proxy creation without payment".center(self.LOG_TITLE_WIDTH, '-'))
        safe_address, safe_instance, owners, funder, fund_amount = self.deploy_safe()

        balance = w3.eth.getBalance(safe_address)
        self.assertEquals(fund_amount, balance)

        # address to,
        # uint256 value, send 0.05 ETH
        # bytes data,
        # Enum.Operation operation,
        # uint256 nonce
        tx_hash_owner0 = safe_instance.functions.approveTransactionWithParameters(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).transact({
            'from': owners[0]
        })

        internal_tx_hash_owner0 = safe_instance.functions.getTransactionHash(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).call({
            'from': owners[0]
        })

        is_approved = safe_instance.functions.isApproved(internal_tx_hash_owner0.hex(), owners[0]).call()
        self.assertTrue(is_approved)

        transaction_data = {
            'sender': owners[0],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'safe': safe_address,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()
        }

        serializer = SafeMultisigTransactionSerializer(data=transaction_data)
        self.assertTrue((serializer.is_valid()))

        # Save
        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=serializer.data, format='json')
        self.assertEquals(request.status_code, status.HTTP_201_CREATED)

        db_safe_transactions = MultisigTransaction.objects.filter(safe=safe_address, to=owners[0],
                                                                  value=self.WITHDRAW_AMOUNT, data=b'',
                                                                  operation=self.CALL, nonce=safe_nonce)

        self.assertEquals(db_safe_transactions.count(), 1)

        # Send Tx signed by owner 2
        tx_hash_owner1 = safe_instance.functions.approveTransactionWithParameters(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).transact({
            'from': owners[1]
        })

        internal_tx_hash_owner1 = safe_instance.functions.getTransactionHash(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).call({
            'from': owners[1]
        })

        is_approved = safe_instance.functions.isApproved(internal_tx_hash_owner1.hex(), owners[1]).call()
        self.assertTrue(is_approved)

        # Send confirmation from owner1 to API
        transaction_data = {
            'sender': owners[1],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'safe': safe_address,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner1.hex()
        }

        serializer = SafeMultisigTransactionSerializer(data=transaction_data)
        self.assertTrue((serializer.is_valid()))

        # Save
        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=serializer.data, format='json')
        self.assertEquals(request.status_code, status.HTTP_201_CREATED)

        # Execute Multisig Transaction
        tx_hash_owner2 = safe_instance.functions.execTransactionIfApproved(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).transact({
            'from': owners[2]
        })

        internal_tx_hash_owner2 = safe_instance.functions.getTransactionHash(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).call({
            'from': owners[2]
        })

        is_executed = safe_instance.functions.isExecuted(internal_tx_hash_owner2.hex()).call()
        self.assertTrue(is_executed)

        # Send confirmation from owner2 to API
        transaction_data = {
            'sender': owners[2],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'safe': safe_address,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner2.hex()
        }

        serializer = SafeMultisigTransactionSerializer(data=transaction_data)
        self.assertTrue((serializer.is_valid()))

        # Save
        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=serializer.data, format='json')
        self.assertEquals(request.status_code, status.HTTP_201_CREATED)

        balance = w3.eth.getBalance(safe_address)
        self.assertEquals(fund_amount-self.WITHDRAW_AMOUNT, balance)

        # Get multisig transaction data
        request = self.client.get(reverse('v1:get-multisig-transactions', kwargs={'address': safe_address}),
                                  format='json')
        self.assertEquals(request.status_code, status.HTTP_200_OK)
        self.assertEquals(len(json.loads(request.content)), 1)
        self.assertEquals(len(json.loads(request.content)[0]['confirmations']), 3)
        self.assertEquals(json.loads(request.content)[0]['confirmations'][2]['owner'], owners[0]) # confirmations are sorted by creation date DESC

    def test_create_multisig_invalid_transaction_parameters(self):
        safe_address, safe_instance, owners, funder, fund_amount = self.deploy_safe()
        self.assertIsNotNone(safe_address)
        safe_nonce = randint(0, 10)

        tx_hash_owner0 = safe_instance.functions.approveTransactionWithParameters(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).transact({
            'from': owners[0]
        })

        internal_tx_hash_owner0 = safe_instance.functions.getTransactionHash(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).call({
            'from': owners[0]
        })

        # Call API with invalid contract_transaction_hash sent by owner1 to API
        transaction_data = {
            'sender': owners[0],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()[0:-2]
        }

        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=transaction_data, format='json')
        self.assertEquals(request.status_code, status.HTTP_400_BAD_REQUEST)

        # Use correct contract_transaction_hash
        transaction_data = {
            'sender': owners[0],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()
        }

        # Create wrong safe address
        wrong_safe_address = safe_address[:-5] + 'fffff' # not checksumed address

        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': wrong_safe_address}),
                                   data=transaction_data, format='json')
        self.assertEquals(request.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        with self.assertRaises(MultisigTransaction.DoesNotExist):
            MultisigTransaction.objects.get(safe=safe_address, nonce=safe_nonce)

        with self.assertRaises(MultisigConfirmation.DoesNotExist):
            MultisigConfirmation.objects.get(owner=owners[0], contract_transaction_hash=internal_tx_hash_owner0.hex())

        # Create invalid not base16 address
        wrong_safe_address = safe_address[:-4] + 'test'  # not base16 address
        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': wrong_safe_address}),
                                   data=transaction_data, format='json')
        self.assertEquals(request.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        with self.assertRaises(MultisigTransaction.DoesNotExist):
            MultisigTransaction.objects.get(safe=safe_address, nonce=safe_nonce)

        with self.assertRaises(MultisigConfirmation.DoesNotExist):
            MultisigConfirmation.objects.get(owner=owners[0], contract_transaction_hash=internal_tx_hash_owner0.hex())

        # Call API using wrong sender (owner1), which has not been approved yet
        transaction_data = {
            'sender': owners[1],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()
        }

        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=transaction_data, format='json')
        self.assertEquals(request.status_code, status.HTTP_400_BAD_REQUEST)

        with self.assertRaises(MultisigTransaction.DoesNotExist):
            MultisigTransaction.objects.get(safe=safe_address, nonce=safe_nonce)

        with self.assertRaises(MultisigConfirmation.DoesNotExist):
            MultisigConfirmation.objects.get(owner=owners[0], contract_transaction_hash=internal_tx_hash_owner0.hex())
            MultisigConfirmation.objects.get(owner=owners[1], contract_transaction_hash=internal_tx_hash_owner0.hex())

        # Call API using invalid sender address
        transaction_data = {
            'sender': owners[0][:-5] + 'fffff',
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()
        }
        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=transaction_data, format='json')
        self.assertEquals(request.status_code, status.HTTP_400_BAD_REQUEST)
        with self.assertRaises(MultisigTransaction.DoesNotExist):
            MultisigTransaction.objects.get(safe=safe_address, nonce=safe_nonce)

        with self.assertRaises(MultisigConfirmation.DoesNotExist):
            MultisigConfirmation.objects.get(owner=owners[0], contract_transaction_hash=internal_tx_hash_owner0.hex())
            MultisigConfirmation.objects.get(owner=owners[1], contract_transaction_hash=internal_tx_hash_owner0.hex())

        # Call API using invalid 'to' address
        transaction_data = {
            'sender': owners[0][:-5] + 'fffff',
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()
        }
        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=transaction_data, format='json')
        self.assertEquals(request.status_code, status.HTTP_400_BAD_REQUEST)
        with self.assertRaises(MultisigTransaction.DoesNotExist):
            MultisigTransaction.objects.get(safe=safe_address, nonce=safe_nonce)

        with self.assertRaises(MultisigConfirmation.DoesNotExist):
            MultisigConfirmation.objects.get(owner=owners[0], contract_transaction_hash=internal_tx_hash_owner0.hex())
            MultisigConfirmation.objects.get(owner=owners[1], contract_transaction_hash=internal_tx_hash_owner0.hex())

        # Call API with correct data values and parameters
        transaction_data = {
            'sender': owners[0],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()
        }
        request = self.client.post(reverse('v1:create-multisig-transactions', kwargs={'address': safe_address}),
                                   data=transaction_data, format='json')
        self.assertEquals(request.status_code, status.HTTP_201_CREATED)
        self.assertEquals(MultisigTransaction.objects.filter(safe=safe_address, nonce=safe_nonce).count(), 1)
        self.assertEquals(MultisigConfirmation.objects.filter(
            owner=owners[0], contract_transaction_hash=internal_tx_hash_owner0.hex()).count(), 1)

    def test_create_multisig_invalid_owner(self):
        safe_address, safe_instance, owners, funder, fund_amount = self.deploy_safe()
        self.assertIsNotNone(safe_address)
        safe_nonce = randint(0, 10)

        tx_hash_owner0 = safe_instance.functions.approveTransactionWithParameters(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).transact({
            'from': owners[0]
        })

        internal_tx_hash_owner0 = safe_instance.functions.getTransactionHash(
            owners[0], self.WITHDRAW_AMOUNT, b'', 0, safe_nonce
        ).call({
            'from': owners[0]
        })

        # Send confirmation from owner1 to API
        transaction_data = {
            'sender': owners[1],
            'to': owners[0],
            'value': self.WITHDRAW_AMOUNT,
            'safe': safe_address,
            'operation': self.CALL,
            'nonce': safe_nonce,
            'data': b'',
            'contract_transaction_hash': internal_tx_hash_owner0.hex()[0:-2]
        }

        serializer = SafeMultisigTransactionSerializer(data=transaction_data)
        self.assertFalse((serializer.is_valid()))

        transaction_data['contract_transaction_hash'] = internal_tx_hash_owner0.hex()
        serializer = SafeMultisigTransactionSerializer(data=transaction_data)
        self.assertTrue((serializer.is_valid()))

    def test_get_multisig_info(self):
        safe_address, safe_instance, owners, funder, fund_amount = self.deploy_safe()
        safe_nonce = randint(0, 10)

        request = self.client.get(reverse('v1:get-multisig-transactions', kwargs={'address': safe_address}),
                                  format='json')
        self.assertEquals(request.status_code, status.HTTP_404_NOT_FOUND)

        multisig_transaction_instance = MultisigTransactionFactory()
        request = self.client.get(reverse('v1:get-multisig-transactions', kwargs={'address': multisig_transaction_instance.safe}),
                                  format='json')
        self.assertEquals(request.status_code, status.HTTP_200_OK)
        self.assertEquals(len(json.loads(request.content)), 1)
        self.assertEquals(len(json.loads(request.content)[0]['confirmations']), 0)

        multisig_confirmation_instance = MultisigTransactionConfirmationFactory(
            multisig_transaction=multisig_transaction_instance)
        request = self.client.get(reverse('v1:get-multisig-transactions',
                                          kwargs={'address': multisig_confirmation_instance.multisig_transaction.safe}),
                                  format='json')
        self.assertEquals(request.status_code, status.HTTP_200_OK)
        self.assertEquals(len(json.loads(request.content)), 1)
        self.assertEquals(len(json.loads(request.content)[0]['confirmations']), 1)