class ErrorParqueo(Exception):
    def __init__(self,mensaje,status=400):
        self.mensaje,self.status=mensaje,status
        super().__init__(mensaje)
