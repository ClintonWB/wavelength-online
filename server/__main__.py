from wavelength import app,HOST,PORT
import aiohttp
aiohttp.web.run_app(app, host=HOST, port=PORT)