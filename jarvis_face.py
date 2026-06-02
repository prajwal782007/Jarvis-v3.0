import threading
import tkinter as tk
import pyttsx3

engine = pyttsx3.init()
root = None
canvas = None
mouth = None
speaking = False


def animate_mouth():
    global speaking, mouth, canvas
    if root is None or canvas is None or mouth is None:
        return

    if speaking:
        canvas.coords(mouth, 160, 240, 240, 280)
    else:
        canvas.coords(mouth, 170, 250, 230, 260)

    root.after(200, animate_mouth)


def jarvis_speak(text):
    global speaking

    if not isinstance(text, str):
        text = str(text)

    speaking = True
    engine.say(text)
    engine.runAndWait()
    speaking = False


def start_jarvis_face():
    global root, canvas, mouth

    root = tk.Tk()
    root.title("Jarvis Face")

    canvas = tk.Canvas(root, width=400, height=400, bg="black")
    canvas.pack()

    # Eyes
    canvas.create_oval(100, 150, 150, 200, fill="white")
    canvas.create_oval(250, 150, 300, 200, fill="white")

    # Mouth
    mouth = canvas.create_rectangle(170, 250, 230, 260, fill="white")

    animate_mouth()
    root.mainloop()
 