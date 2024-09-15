import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_polling
import aiofiles
import aiohttp
import os
import subprocess
import wave
from vosk import Model, KaldiRecognizer

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен, который вы получили от BotFather
TOKEN = 'your token'

# Создание бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Укажите путь к модели Vosk
vosk_model_path = "vosk-model-small-ru-0.22"
model = Model(vosk_model_path)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Отправь мне голосовое сообщение, и я расшифрую его.")

# Функция для конвертации аудио
def convert_to_wav(input_file, output_file):
    command = ['ffmpeg', '-y', '-i', input_file, output_file]
    subprocess.run(command, check=True)

@dp.message_handler(content_types=types.ContentType.VOICE)
async def handle_voice(message: types.Message):
    voice = message.voice
    file_info = await bot.get_file(voice.file_id)
    file_path = file_info.file_path

    # Скачивание файла
    file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    ogg_file_path = f"{message.from_user.id}.ogg"
    wav_file_path = f"{message.from_user.id}.wav"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status == 200:
                async with aiofiles.open(ogg_file_path, mode='wb') as f:
                    await f.write(await resp.read())

    # Конвертация .ogg файла в .wav
    try:
        convert_to_wav(ogg_file_path, wav_file_path)
        logger.info(f"Файл {ogg_file_path} успешно конвертирован в {wav_file_path}.")
    except Exception as e:
        await bot.send_message(chat_id=message.chat.id, text='Ошибка конвертации аудио файла.')
        logger.error(f"Ошибка конвертации: {e}")
        return

    # Проверка существования .wav файла
    if not os.path.exists(wav_file_path):
        await bot.send_message(chat_id=message.chat.id, text='Ошибка: файл .wav не был создан.')
        logger.error("Файл .wav не был создан.")
        return

    # Распознавание речи с использованием Vosk
    try:
        wf = wave.open(wav_file_path, "rb")
        logger.info(f"Формат аудио: {wf.getnchannels()} каналов, {wf.getsampwidth()} байт, {wf.getframerate()} Гц")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() not in [8000, 16000, 48000]:
            await message.reply("Неправильный формат аудио. Пожалуйста, отправьте голосовое сообщение заново.")
            wf.close()
            return

        rec = KaldiRecognizer(model, wf.getframerate())
        text = ""
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = rec.Result()
                logger.info(f"Результат распознавания (AcceptWaveform): {result}")
                text += result[14:-3]  # Извлекаем распознанный текст из результата
            else:
                result_partial = rec.PartialResult()
                logger.info(f"Частичный результат распознавания (PartialResult): {result_partial}")

        # Последний результат для завершения распознавания
        final_result = rec.FinalResult()
        logger.info(f"Последний результат распознавания (FinalResult): {final_result}")
        text += final_result[14:-3]

        wf.close()

        if text:
            await message.reply(f'Расшифровка: {text}')
        else:
            await bot.send_message(chat_id=message.chat.id, text='Извините, я не смог разобрать это голосовое сообщение.')

    except Exception as e:
        await bot.send_message(chat_id=message.chat.id, text='Ошибка при обработке аудио файла.')
        logger.error(f"Ошибка обработки: {e}")

    # Удаление временных файлов
    if os.path.exists(ogg_file_path):
        os.remove(ogg_file_path)
    if os.path.exists(wav_file_path):
        os.remove(wav_file_path)

if __name__ == '__main__':
    start_polling(dp, skip_updates=True)
