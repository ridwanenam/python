import pygame
from pygame.locals import *
import cv2
from ultralytics import YOLO 
import serial
import json

pygame.init()

serial_port = "/dev/ttyACM0"  # port ke USB 2.0 raspberry
baud_rate = 9600
arduino = serial.Serial(serial_port, baud_rate)

SCREEN_WIDTH = 900
SCREEN_HEIGHT = 350
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Dashboard Smart Recycle Bin")

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (50, 50, 50)
ELEGANT_BORDER = (100, 100, 100)
WHITE_RED = (255, 68, 68)
WHITE_GREEN = (175, 243, 1)
BLUE_TOSCA = (7, 217, 160)
DARK_BLUE = (7, 53, 66)
TEAL = (0, 128, 128)

font = pygame.font.SysFont("Arial", 20)
large_font = pygame.font.SysFont("Arial", 30)
font2 = pygame.font.SysFont("Arial", 23)

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not cap.isOpened():
    print("Error to open video capture.")
    pygame.quit()
    exit()

# ========= MODEL =========
model_path = ("yolov8n.pt")
model = YOLO(model_path)

# rencana indeks: 0 - organik, 1 - anorganik, 2 - B3
objects_to_detect = [0, 1, 2]
last_detected = None

def render_text_with_outline(text, font, text_color, outline_color):
    base = font.render(text, True, outline_color)
    outline = font.render(text, True, text_color)
    outline_surface = pygame.Surface((base.get_width() + 2, base.get_height() + 2), pygame.SRCALPHA)
    outline_surface.blit(base, (1, 0))
    outline_surface.blit(base, (-1, 0))
    outline_surface.blit(base, (0, 1))
    outline_surface.blit(base, (0, -1))
    outline_surface.blit(outline, (0, 0))
    return outline_surface

def draw_button(x, y, width, height, color, text, text_color=WHITE, border_color=ELEGANT_BORDER, border_radius=2):
    pygame.draw.rect(screen, border_color, (x, y, width, height), border_radius)
    pygame.draw.rect(screen, color, (x + 2, y + 2, width - 4, height - 4), border_radius)
    label = render_text_with_outline(text, font, text_color, WHITE)
    text_rect = label.get_rect(center=(x + width // 2, y + height // 2))
    screen.blit(label, text_rect)
    return pygame.Rect(x, y, width, height)

def draw_progress_bar(x, y, width, height, progress, label_text):
    pygame.draw.rect(screen, GRAY, (x, y, width, height), border_radius=5)
    pygame.draw.rect(screen, TEAL, (x, y, width * progress, height), border_radius=5)
    label = render_text_with_outline(label_text, font, WHITE, BLACK)
    screen.blit(label, (x, y - 25))

def draw_frame(x, y, width, height, frame=None, fps=None):
    # Border (80% transparency)
    surface = pygame.Surface((width + 10, height + 10), pygame.SRCALPHA)
    surface.fill((0, 0, 0, 0))
    for i in range(0, width + 10, 10):
        pygame.draw.line(surface, (255, 255, 255, 200), (i, 0), (i + 5, 0), 5)  # Top border
        pygame.draw.line(surface, (255, 255, 255, 200), (i, height + 9), (i + 5, height + 9), 5)  # Bottom border
    for i in range(0, height + 10, 10):
        pygame.draw.line(surface, (255, 255, 255, 200), (0, i), (0, i + 5), 5)  # Left border
        pygame.draw.line(surface, (255, 255, 255, 200), (width + 9, i), (width + 9, i + 5), 5)  # Right border
    screen.blit(surface, (x - 5, y - 5))

    if frame is not None:
        frame_surface = pygame.image.frombuffer(frame.tobytes(), frame.shape[1::-1], "BGR")
        frame_surface = pygame.transform.scale(frame_surface, (width, height))
        screen.blit(frame_surface, (x, y))

    if fps is not None:
        fps_text = f"FPS: {fps:.1f}"
        fps_surface = render_text_with_outline(fps_text, font, BLUE_TOSCA, WHITE)
        screen.blit(fps_surface, (x + 10, y - 28))

current_mode = "Manual"  # default mode
progress_values = {"ORGANIK": 0, "ANORGANIK": 0, "B3": 0}

def calculate_progress(distance):
    if distance <= 10:
        return 1.0
    elif distance >= 100:
        return 0.0
    else:
        return max(0, (100 - distance) / 100)

# transfer data ultrasonik
def read_arduino_data():
    try:
        if arduino.in_waiting > 0:
            data = arduino.readline().decode('utf-8').strip() 
            distances = json.loads(data)  # parsing data JSON
            
            # Update progress values
            progress_values["ORGANIK"] = calculate_progress(distances["organik"])
            progress_values["ANORGANIK"] = calculate_progress(distances["anorganik"])
            progress_values["B3"] = calculate_progress(distances["b3"])

            # buzzer
            if distances["organik"] > 90 or distances["anorganik"] > 90 or distances["b3"] > 90:
                send_command_to_arduino("BuzzerON")
            else:
                send_command_to_arduino("BuzzerOFF")
                
    except json.JSONDecodeError:
        print(f"Error decoding JSON: {data}")  # error parsing JSON
    except Exception as e:
        print(f"Error reading serial data: {e}")

def send_command_to_arduino(command):
    try:
        arduino.write(command.encode())
    except Exception as e:
        print(f"Error sending command: {e}")

running = True

while running:
    screen.fill(DARK_GRAY)
    read_arduino_data()

    # frame dari kamera
    ret, frame = cap.read()
    if not ret:
        print("can't read frame.")
        continue 

    # object detection di frame
    results = model(frame, imgsz=160)
    detected_objects = results[0].boxes.cls.tolist()  # ID objek detected

    detected_object = None
    for obj_id in detected_objects:
        if obj_id in objects_to_detect:
            detected_object = obj_id
            break 

    if detected_object is not None and detected_object != last_detected:
        last_detected = detected_object

        if detected_object == 0:
            print("Sampah Organik Terdetect")
            if current_mode == "Auto":
                send_command_to_arduino("AutoOrganik")  
        elif detected_object == 1:
            print("Sampah Anorganik Terdetect")
            if current_mode == "Auto":
                send_command_to_arduino("AutoAnorganik")  
        elif detected_object == 2:
            print("Sampah B3 Terdetect")
            if current_mode == "Auto":
                send_command_to_arduino("AutoB3")  

    # frame hasil deteksi
    annotated_frame = results[0].plot()

    # mode dan kontrol
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False

        if event.type == MOUSEBUTTONDOWN:
            mouse_pos = pygame.mouse.get_pos()
            if btn_auto.collidepoint(mouse_pos):
                current_mode = "Auto"
                print("Mode: Auto")
                send_command_to_arduino("Auto")
            elif btn_manual.collidepoint(mouse_pos):
                current_mode = "Manual"
                print("Mode: Manual")
                send_command_to_arduino("Manual")
            elif btn_left.collidepoint(mouse_pos) and current_mode == "Manual":
                print("LEFT")
                send_command_to_arduino("LEFT")
            elif btn_right.collidepoint(mouse_pos) and current_mode == "Manual":
                print("RIGHT")
                send_command_to_arduino("RIGHT")
            elif btn_servo.collidepoint(mouse_pos) and current_mode == "Manual":
                print("OPEN")
                send_command_to_arduino("OPEN")
            elif btn_reset.collidepoint(mouse_pos) and current_mode in ["Auto", "Manual"]:
                print("RESET")
                send_command_to_arduino("RESET")

    # header
    pygame.draw.rect(screen, BLUE_TOSCA, (0, 0, SCREEN_WIDTH, 50))
    header_text = render_text_with_outline("DASHBOARD SMART RECYCLE BIN", large_font, WHITE, BLACK)
    screen.blit(header_text, (20, 10))

    # FPS dan frame kamera
    inference_time = results[0].speed['inference']
    fps = 1000 / inference_time
    draw_frame(250, 85, 400, 250, annotated_frame, fps)

    # progress bar volume sampah
    pygame.draw.rect(screen, WHITE, (15, 105, 225, 210), border_radius=15)
    pygame.draw.rect(screen, BLACK, (20, 110, 215, 200), border_radius=10)
    volume_text = render_text_with_outline("VOLUME SAMPAH", font2, BLUE_TOSCA, WHITE)
    screen.blit(volume_text, (30, 120))

    bar_start_y = 180
    for i, (label, value) in enumerate(progress_values.items()):
        draw_progress_bar(30, bar_start_y + i * 50, 160, 20, value, label)

    # tombol mode
    pygame.draw.rect(screen, WHITE, (660, 80, 225, 90), border_radius=5)
    pygame.draw.rect(screen, BLACK, (665, 85, 215, 80), border_radius=5)
    mode_text = render_text_with_outline("MODE", font2, BLUE_TOSCA, WHITE)
    screen.blit(mode_text, (734, 88))

    btn_auto = draw_button(700, 120, 60, 37, BLUE_TOSCA if current_mode == "Auto" else GRAY, "A")
    btn_manual = draw_button(780, 120, 60, 37, BLUE_TOSCA if current_mode == "Manual" else GRAY, "M")

    # tombol kontrol
    pygame.draw.rect(screen, WHITE, (660, 185, 225, 145), border_radius=15)
    pygame.draw.rect(screen, BLACK, (665, 190, 215, 135), border_radius=10)
    stepper_text = render_text_with_outline("CONTROL", font2, BLUE_TOSCA, WHITE)
    screen.blit(stepper_text, (717, 197))

    btn_left = draw_button(680, 230, 80, 40, BLUE_TOSCA, "LEFT")
    btn_right = draw_button(780, 230, 80, 40, BLUE_TOSCA, "RIGHT")
    btn_reset = draw_button(680, 277, 80, 40, BLUE_TOSCA, "RESET")
    btn_servo = draw_button(780, 277, 80, 40, BLUE_TOSCA, "OPEN")

    pygame.display.update()

cap.release()
pygame.quit()

