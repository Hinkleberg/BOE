extends Node3D

var socket: StreamPeerTCP = StreamPeerTCP.new()

func _ready():
	var err = socket.connect_to_host("127.0.0.1", 7500)
	print("connect_to_host:", err)

func _process(_delta):
	if socket.get_status() == StreamPeerTCP.STATUS_CONNECTING:
		socket.poll()
	elif socket.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		var bytes := socket.get_available_bytes()
		if bytes > 0:
			var packet = socket.get_data(bytes)
			print(packet)
