from django.test import TestCase
from django.test.client import Client
from django.contrib.auth.models import User
from django.core import mail
import socket, select
import threading
import pprint

from lighting.models import *
from lighting.pjlink import PJLinkCommandLine, PJLinkResponse, PJLinkAuthenticationRequest, PJLinkAuthenticationException, PJLinkProtocol, PJLinkController

APP_PATH = '/lighting/'

class MockPJLinkProjector(threading.Thread):
	"""This creates a localhost server socket which speaks the PJLink protocol as if it were a projector"""
	def __init__(self):
		self.backlog = 5 
		self.buffer_size = 1024
		self.server = None
		self.running = False

		self.projector_name = "The Projector in the Blue Room"
		self.manufacture_name = "2038 Problems, Inc."
		self.product_name = "Big Bad Projector 1900"
		self.other_info = "This Thing Rocks (tm)"
		self.class_info = "1"

		self.password = 'squarePusher' # or None if the projector should use no auth

		self.power_state = PJLinkProtocol.POWER_OFF_STATUS
		self.input = [PJLinkProtocol.RGB_INPUT, PJLinkProtocol.INPUT_1]
		self.available_inputs = [[PJLinkProtocol.RGB_INPUT, PJLinkProtocol.INPUT_1], [PJLinkProtocol.VIDEO_INPUT, PJLinkProtocol.INPUT_2]]
		self.audio_mute = False
		self.video_mute = False
		
		self.errors = [['fan', PJLinkProtocol.ERROR_STATUS_OK], ['lamp', PJLinkProtocol.ERROR_STATUS_OK], ['filter', PJLinkProtocol.ERROR_STATUS_OK], ['cover', PJLinkProtocol.ERROR_STATUS_OK], ['other', PJLinkProtocol.ERROR_STATUS_OK]]
		
		# an array of arrays [[lighting time, lamp is on], ...]
		self.lamps = [[100, False], [500, False], [0, False]]

		threading.Thread.__init__(self)

	def _set_mute_state(self, state):
		if state == PJLinkProtocol.AUDIO_VIDEO_MUTE_ON:
			self.audio_mute = True
			self.video_mute = True
		elif state == PJLinkProtocol.AUDIO_MUTE_ON:
			self.audio_mute = True
		elif state == PJLinkProtocol.VIDEO_MUTE_ON:
			self.video_mute = True
		elif state == PJLinkProtocol.AUDIO_MUTE_OFF:
			self.audio_mute = False
		elif state == PJLinkProtocol.VIDEO_MUTE_OFF:
			self.video_mute = False
		elif state == PJLinkProtocol.AUDIO_VIDEO_MUTE_OFF:
			self.audio_mute = False
			self.video_mute = False
		else:
			return False
		return True
		
	def _get_mute_state(self):
		if self.audio_mute and self.video_mute:
			return PJLinkProtocol.AUDIO_VIDEO_MUTE_ON
		elif self.audio_mute: 
			return PJLinkProtocol.AUDIO_MUTE_ON
		elif self.video_mute:
			return PJLinkProtocol.VIDEO_MUTE_ON
		else:
			return PJLinkProtocol.AUDIO_VIDEO_MUTE_OFF

	mute_state = property(_get_mute_state, _set_mute_state)
			
	def stop_server(self):
		self.running = False
		self.server.close()
	
	def run(self): 
		if self.running: return
		self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
		#self.server.settimeout(5)
		self.server.bind(('127.0.0.1',0)) 
		self.server.listen(self.backlog)
		self.running = True
		while self.running:
			client, address = self.server.accept()
			auth_request = PJLinkAuthenticationRequest(self.password)
			client.send(auth_request.encode())
			data = client.recv(self.buffer_size) 
			if not data:
				client.close()
				continue

			response = None 
			command_line = PJLinkCommandLine.decode(data)

			if not auth_request.authentication_hash_matches(command_line.authentication_hash):
				response = PJLinkResponse(PJLinkProtocol.AUTHENTICATE, PJLinkProtocol.INVALID_PASSWORD_ERROR, version=None)
				client.send(response.encode())
				client.close()
				continue
				
			if command_line.command == PJLinkProtocol.POWER:
				if command_line.data == PJLinkProtocol.ON or command_line.data == PJLinkProtocol.OFF:
					self.power_state = command_line.data
					for lamp in self.lamps: lamp[1] = command_line.data == PJLinkProtocol.ON
					response = PJLinkResponse(PJLinkProtocol.POWER, PJLinkProtocol.OK)
				elif command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(PJLinkProtocol.POWER, self.power_state)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.INPUT:
				if command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(command_line.command, '%s%s' % (self.input[0], self.input[1]))
				elif len(command_line.data) == 2:
					self.input = [command_line.data[0], command_line.data[1]]
					response = PJLinkResponse(command_line.command, PJLinkProtocol.OK)
				else:
					response = PJLinkResponse(command_line.commands, PJLinkProtocol.ERROR_2)
					
			elif command_line.command == PJLinkProtocol.AVAILABLE_INPUTS:
				if command_line.data == PJLinkProtocol.QUERY:
					data = ' '.join(['%s%s' % (input[0], input[1]) for input in self.available_inputs])
					response = PJLinkResponse(command_line.command, data)
				else:
					response = PJLinkResponse(command_line.commands, PJLinkProtocol.ERROR_2)
					
			elif command_line.command == PJLinkProtocol.MUTE:
				if command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(command_line.command, self.mute_state)
				elif command_line.data == PJLinkProtocol.AUDIO_VIDEO_MUTE_ON or command_line.data == PJLinkProtocol.AUDIO_VIDEO_MUTE_OFF or command_line.data == PJLinkProtocol.VIDEO_MUTE_ON or command_line.data == PJLinkProtocol.VIDEO_MUTE_OFF or command_line.data == PJLinkProtocol.AUDIO_MUTE_ON or command_line.data == PJLinkProtocol.AUDIO_MUTE_OFF:
					self.mute_state = command_line.data
					response = PJLinkResponse(command_line.command, PJLinkProtocol.OK)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.NAME:
				if command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(command_line.command, self.projector_name)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.MANUFACTURE_NAME:
				if command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(command_line.command, self.manufacture_name)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.PRODUCT_NAME:
				if command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(command_line.command, self.product_name)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.OTHER_INFO:
				if command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(command_line.command, self.other_info)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.CLASS_INFO:
				if command_line.data == PJLinkProtocol.QUERY:
					response = PJLinkResponse(command_line.command, self.class_info)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.ERROR_STATUS:
				if command_line.data == PJLinkProtocol.QUERY:
					data = ''.join([error[1] for error in self.errors])
					response = PJLinkResponse(command_line.command, data)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			elif command_line.command == PJLinkProtocol.LAMP:
				if command_line.data == PJLinkProtocol.QUERY:
					data = ' '.join(['%s %s' % (lamp[0], '1' if lamp[1] == True else '0') for lamp in self.lamps])
					response = PJLinkResponse(command_line.command, data)
				else:
					response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_2)

			else:
				response = PJLinkResponse(command_line.command, PJLinkProtocol.ERROR_1)
				
			client.send(response.encode())
			client.close()
			
		self.server.close()
		
class PJLinkTest(TestCase):
	def setUp(self):
		pass
	def tearDown(self):
		pass
	
	def test_controller(self):
		projector = MockPJLinkProjector()
		projector.start()
		seconds_to_wait = 5
		while projector.running == False and seconds_to_wait > 0:
			time.sleep(1)
			seconds_to_wait -= 1
		self.failUnless(projector.running)

		# Connection and authentication
		bad_controller = PJLinkController(projector.server.getsockname()[0], projector.server.getsockname()[1], password='badPassword')
		try:
			bad_controller.query_name()
			self.fail() # should have thrown an authentication exception
		except PJLinkAuthenticationException:
			pass # this is what should happen
		projector.password = None
		unauth_controller = PJLinkController(projector.server.getsockname()[0], projector.server.getsockname()[1], password=None)
		try:
			unauth_controller.query_name()
		except PJLinkAuthenticationException:
			self.fail() # should not throw an authentication exception because both think there's no password
		projector.password = 'moceanWorker'
		controller = PJLinkController(projector.server.getsockname()[0], projector.server.getsockname()[1], password=projector.password)
		try:
			self.failUnlessEqual(controller.query_name(), projector.projector_name)
		except PJLinkAuthenticationException:
			self.fail() # should not throw an authentication exception because they agree on the password

		# Power setting, querying
		self.failUnless(projector.lamps[0][1] == False)
		self.failUnlessEqual(controller.query_power(), PJLinkProtocol.POWER_OFF_STATUS)
		self.failUnless(controller.power_on())
		self.failUnlessEqual(controller.query_power(), PJLinkProtocol.POWER_ON_STATUS)
		self.failUnless(projector.lamps[0][1] == True)
		self.failUnless(controller.power_off())
		self.failUnlessEqual(controller.query_power(), PJLinkProtocol.POWER_OFF_STATUS)
		self.failUnless(projector.lamps[0][1] == False)

		controller.power_on()
		
		# Input querying and setting
		input_state, input_number = controller.query_input()
		self.failUnlessEqual(input_state, PJLinkProtocol.RGB_INPUT)
		self.failUnlessEqual(input_number, PJLinkProtocol.INPUT_1)
		self.failUnless(controller.set_input(PJLinkProtocol.RGB_INPUT, PJLinkProtocol.INPUT_2))
		input_state, input_number = controller.query_input()
		self.failUnlessEqual(input_state, PJLinkProtocol.RGB_INPUT)
		self.failUnlessEqual(input_number, PJLinkProtocol.INPUT_2)
		self.failUnless(controller.set_input(PJLinkProtocol.VIDEO_INPUT, PJLinkProtocol.INPUT_3))
		input_state, input_number = controller.query_input()
		self.failUnlessEqual(input_state, PJLinkProtocol.VIDEO_INPUT)
		self.failUnlessEqual(input_number, PJLinkProtocol.INPUT_3)

		# Available inputs
		available_inputs = controller.query_available_inputs()
		self.failUnlessEqual(len(available_inputs), len(projector.available_inputs))
		for index, available_input in enumerate(projector.available_inputs):
			self.failUnlessEqual(available_inputs[index][0], projector.available_inputs[index][0])
			self.failUnlessEqual(available_inputs[index][1], projector.available_inputs[index][1])

		# Muting
		audio_mute, video_mute = controller.query_mute()
		self.failUnlessEqual(audio_mute, False)
		self.failUnlessEqual(video_mute, False)
		self.failUnless(controller.set_mute(PJLinkProtocol.AUDIO_VIDEO_MUTE_ON))
		audio_mute, video_mute = controller.query_mute()
		self.failUnlessEqual(audio_mute, True)
		self.failUnlessEqual(video_mute, True)
		self.failUnless(controller.set_mute(PJLinkProtocol.AUDIO_MUTE_OFF))
		self.failUnless(controller.set_mute(PJLinkProtocol.VIDEO_MUTE_ON))
		audio_mute, video_mute = controller.query_mute()
		self.failUnlessEqual(audio_mute, False)
		self.failUnlessEqual(video_mute, True)
		self.failUnless(controller.set_mute(PJLinkProtocol.AUDIO_MUTE_ON))
		self.failUnless(controller.set_mute(PJLinkProtocol.VIDEO_MUTE_OFF))
		audio_mute, video_mute = controller.query_mute()
		self.failUnlessEqual(audio_mute, True)
		self.failUnlessEqual(video_mute, False)

		# Error status
		fan_status, lamp_status, filter_status, cover_status, other_status = controller.query_error_status()
		self.failUnlessEqual(fan_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(lamp_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(filter_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(cover_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(other_status, PJLinkProtocol.ERROR_STATUS_OK)
		projector.errors[0][1] = PJLinkProtocol.ERROR_STATUS_ERROR
		fan_status, lamp_status, filter_status, cover_status, other_status = controller.query_error_status()
		self.failUnlessEqual(fan_status, PJLinkProtocol.ERROR_STATUS_ERROR)
		self.failUnlessEqual(lamp_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(filter_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(cover_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(other_status, PJLinkProtocol.ERROR_STATUS_OK)
		projector.errors[4][1] = PJLinkProtocol.ERROR_STATUS_ERROR
		fan_status, lamp_status, filter_status, cover_status, other_status = controller.query_error_status()
		self.failUnlessEqual(fan_status, PJLinkProtocol.ERROR_STATUS_ERROR)
		self.failUnlessEqual(lamp_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(filter_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(cover_status, PJLinkProtocol.ERROR_STATUS_OK)
		self.failUnlessEqual(other_status, PJLinkProtocol.ERROR_STATUS_ERROR)

		# LAMPS
		lamp_info = controller.query_lamps()
		self.failUnlessEqual(len(lamp_info), len(projector.lamps))
		for index, lamp in enumerate(projector.lamps):
			self.failUnlessEqual(len(lamp_info[index]), 2)
			self.failUnlessEqual(lamp_info[index][0], projector.lamps[index][0])
			self.failUnlessEqual(lamp_info[index][1], projector.lamps[index][1])
		controller.power_off()
		lamp_info = controller.query_lamps()
		for index, lamp in enumerate(projector.lamps):
			self.failUnlessEqual(lamp_info[index][0], projector.lamps[index][0])
			self.failUnlessEqual(lamp_info[index][1], projector.lamps[index][1])
		projector.lamps = [[0, False]]
		lamp_info = controller.query_lamps()
		for index, lamp in enumerate(projector.lamps):
			self.failUnlessEqual(lamp_info[index][0], projector.lamps[index][0])
			self.failUnlessEqual(lamp_info[index][1], projector.lamps[index][1])
		
		# INFO
		self.failUnlessEqual(controller.query_name(), projector.projector_name)
		self.failUnlessEqual(controller.query_manufacture_name(), projector.manufacture_name)
		self.failUnlessEqual(controller.query_product_name(), projector.product_name)
		self.failUnlessEqual(controller.query_other_info(), projector.other_info)
		self.failUnlessEqual(controller.query_class_info(), projector.class_info)
		
		projector.stop_server()
		
	def test_codecs(self):
		command1 = PJLinkCommandLine(PJLinkProtocol.POWER, PJLinkProtocol.ON)
		self.failUnlessEqual(command1.version, 1)
		self.failUnlessEqual(command1.command, PJLinkProtocol.POWER)
		self.failUnlessEqual(command1.data, PJLinkProtocol.ON)
		
		command2 = PJLinkCommandLine.decode(command1.encode())
		self.failUnlessEqual(command1.encode(), command2.encode())
		self.failUnlessEqual(command1.command, command2.command)
		self.failUnless(command1.data, command2.data)
		self.failUnless(command1.version, command2.version)
		
		response1 = PJLinkResponse(PJLinkProtocol.POWER, "1")
		self.failUnlessEqual(response1.version, 1)
		self.failUnlessEqual(response1.command, PJLinkProtocol.POWER)
		self.failUnlessEqual(response1.data, "1")
		
		response2 = PJLinkResponse.decode(response1.encode())
		self.failUnlessEqual(response1.encode(), response2.encode())
		self.failUnlessEqual(response1.version, response2.version)
		self.failUnlessEqual(response1.command, response2.command)
		self.failUnlessEqual(response1.data, response2.data)

# Copyright 2009 GORBET + BANERJEE (http://www.gorbetbanerjee.com/) Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0 Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.