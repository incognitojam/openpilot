from cereal import car
from opendbc.can.parser import CANParser
from openpilot.common.conversions import Conversions as CV
from openpilot.selfdrive.car.interfaces import CarStateBase
from openpilot.selfdrive.car.volvo.values import DBC, VolvoFlags


class CarState(CarStateBase):
  def __init__(self, CP):
    super().__init__(CP)

    # C1
    self.cruiseState_enabled_prev = False
    self.count_zero_steeringTorque = 0

  def update(self, cp, cp_cam):
    if self.CP.flags & VolvoFlags.C1:
      return self.update_c1(cp, cp_cam)

    ret = car.CarState.new_message()

    # car speed
    ret.vEgoRaw = cp.vl["VehicleSpeed1"]["VehicleSpeed"] * CV.KPH_TO_MS
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    # ret.standstill = ret.vEgoRaw < 0.1

    # gas pedal
    ret.gas = cp.vl["AccPedal"]["AccPedal"] / 102.3
    ret.gasPressed = ret.gas > 0.1

    # brake pedal
    ret.brake = 0.
    ret.brakePressed = False  # ! TODO

    # steering
    ret.steeringAngleDeg = cp.vl["PSCM1"]["SteeringAngleServo"]
    ret.steeringTorque = cp.vl["PSCM1"]["LKATorque"]
    ret.steeringPressed = False  # TODO

    # Check if servo stops responding when ACC is active
    if ret.cruiseState.enabled and ret.vEgo > self.CP.minSteerSpeed:
      # Reset counter on entry
      if self.cruiseState_enabled_prev != ret.cruiseState.enabled:
        self.count_zero_steeringTorque = 0

      # Count up when no torque from servo detected
      if ret.steeringTorque == 0:
        self.count_zero_steeringTorque += 1
      else:
        self.count_zero_steeringTorque = 0

      # Set fault if above threshold
      ret.steerFaultTemporary = self.count_zero_steeringTorque >= 1000

    # cruise state
    ret.cruiseState.speed = cp.vl["ACC_Speed"]["ACC_Speed"] * CV.KPH_TO_MS
    ret.cruiseState.available = cp_cam.vl["FSM0"]["ACCStatus"] in (2, 6, 7)
    ret.cruiseState.enabled = cp_cam.vl["FSM0"]["ACCStatus"] in (6, 7)
    ret.cruiseState.standstill = cp_cam.vl["FSM3"]["ACC_Standstill"] == 1
    ret.cruiseState.nonAdaptive = False  # TODO
    ret.accFaulted = False
    self.acc_distance = cp_cam.vl["FSM1"]["ACC_Distance"]

    # gear
    ret.gearShifter = car.CarState.GearShifter.drive  # TODO

    # safety
    ret.stockFcw = False  # TODO
    ret.stockAeb = False

    # button presses
    ret.buttonEvents = self.create_button_events(cp, self.CCP.BUTTONS)
    ret.leftBlinker = cp.vl["MiscCarInfo"]["TurnSignal"] == 1
    ret.rightBlinker = cp.vl["MiscCarInfo"]["TurnSignal"] == 3

    # lock info
    ret.doorOpen = False  # TODO
    ret.seatbeltUnlatched = False

    # Store info from servo message PSCM1
    # FSM (camera) checks if LKAActive & LKATorque active when not requested
    self.pscm_stock_values = cp.vl["PSCM1"]

    self.cruiseState_enabled_prev = ret.cruiseState.enabled

    return ret

  def update_c1(self, cp, cp_cam):
    ret = car.CarState.new_message()

    # TODO

    return ret

  @staticmethod
  def get_can_parser(CP):
    if CP.flags & VolvoFlags.C1:
      return CarState.get_can_parser_c1(CP)

    messages = [
      # msg, freq
      ("VehicleSpeed1", 50),
      ("AccPedal", 100),
      ("PSCM1", 50),
      ("ACC_Speed", 50),
      ("MiscCarInfo", 25),
    ]

    return CANParser(DBC[CP.carFingerprint]["pt"], messages, 0)

  @staticmethod
  def get_cam_can_parser(CP):
    messages = [
      # msg, freq
      ("FSM0", 100),
      ("FSM1", 50),
      ("FSM3", 50),
    ]

    return CANParser(DBC[CP.carFingerprint]["pt"], messages, 2)

  @staticmethod
  def get_can_parser_c1(CP):
    messages = [
      # TODO
    ]

    return CANParser(DBC[CP.carFingerprint]["pt"], messages, 0)

  @staticmethod
  def get_cam_can_parser_c1(CP):
    messages = [
      # TODO
    ]

    return CANParser(DBC[CP.carFingerprint]["pt"], messages, 2)
