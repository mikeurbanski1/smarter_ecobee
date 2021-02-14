class Selection:

    def __init__(self,
                 selection_type='registered',
                 selection_match='',
                 includeRuntime=False,
                 includeExtendedRuntime=False,
                 includeElectricity=False,
                 includeSettings=False,
                 includeLocation=False,
                 includeProgram=False,
                 includeEvents=False,
                 includeDevice=False,
                 includeTechnician=False,
                 includeUtility=False,
                 includeAlerts=False,
                 includeWeather=False,
                 includeOemConfig=False,
                 includeEquipmentStatus=False,
                 includeNotificationSettings=False,
                 includePrivacy=False,
                 includeVersion=False,
                 includeSecuritySettings=False,
                 includeSensors=False):
        self.selection_type = selection_type
        self.selection_match = selection_match
        self.includeRuntime = includeRuntime
        self.includeExtendedRuntime = includeExtendedRuntime
        self.includeElectricity = includeElectricity
        self.includeSettings = includeSettings
        self.includeLocation = includeLocation
        self.includeProgram = includeProgram
        self.includeEvents = includeEvents
        self.includeDevice = includeDevice
        self.includeTechnician = includeTechnician
        self.includeUtility = includeUtility
        self.includeAlerts = includeAlerts
        self.includeWeather = includeWeather
        self.includeOemConfig = includeOemConfig
        self.includeEquipmentStatus = includeEquipmentStatus
        self.includeNotificationSettings = includeNotificationSettings
        self.includePrivacy = includePrivacy
        self.includeVersion = includeVersion
        self.includeSecuritySettings = includeSecuritySettings
        self.includeSensors = includeSensors

    def get_selection(self):
        s = {
            'selectionType': self.selection_type,
            'selectionMatch': ''
        }
        s.update({k: True for k in self.__dict__ if 'include' in k and self.__dict__[k]})
        return s
